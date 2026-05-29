import csv
import io
import re
import openpyxl
from django.db.models import Q
from .models import Contact, Category, ImportLog


def _get_or_create_category(user, name):
    name = (name or '').strip()
    if not name:
        return None
    default = Category.objects.filter(user=None, name__iexact=name).first()
    if default:
        return default
    user_cat = Category.objects.filter(user=user, name__iexact=name).first()
    if user_cat:
        return user_cat
    return Category.objects.create(user=user, name=name)


def _is_valid_email(email):
    if not email:
        return True
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))


def _is_duplicate(user, phone, email, exclude_id=None):
    """
    Used by the preview step to count how many rows already exist.
    Exact phone OR exact email match counts as duplicate.
    """
    qs = Contact.objects.filter(user=user)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    if phone and qs.filter(phone_number=phone).exists():
        return True
    if email and qs.filter(email=email).exists():
        return True
    return False


def _is_exact_duplicate(user, name, phone, email):
    """
    Stricter check used at commit time.
    Only skips a row if the name AND (phone or email) both match an existing contact.
    This allows 'Mum, 08012345678' and 'Mama, 08012345678' to both be imported
    so the user can review and merge them in Settings.
    """
    qs = Contact.objects.filter(user=user)
    if phone:
        match = qs.filter(phone_number=phone, full_name__iexact=name).first()
        if match:
            return True
    if email:
        match = qs.filter(email__iexact=email, full_name__iexact=name).first()
        if match:
            return True
    return False


def _normalise_row(name, phone, email, category):
    name     = (name     or '').strip()
    phone    = (phone    or '').strip()
    email    = (email    or '').strip()
    category = (category or '').strip()
    if not name or not phone:
        return None
    return {'name': name, 'phone': phone, 'email': email, 'category': category}


def parse_file_for_preview(file, filename):
    filename = filename.lower()
    if filename.endswith('.csv'):
        return _parse_csv(file)
    elif filename.endswith('.txt'):
        return _parse_txt(file)
    elif filename.endswith('.xlsx'):
        return _parse_xlsx(file)
    else:
        return {'rows': [], 'failed': 0, 'error': 'Unsupported file type. Use CSV, TXT, or XLSX.', 'format': None}


def _parse_csv(file):
    rows   = []
    failed = 0
    try:
        decoded = file.read().decode('utf-8-sig')
        reader  = csv.DictReader(io.StringIO(decoded))
    except Exception:
        return {'rows': [], 'failed': 0, 'error': 'Could not read CSV file.', 'format': 'csv'}

    for raw in reader:
        row = _normalise_row(
            raw.get('name') or raw.get('Name'),
            raw.get('phone') or raw.get('Phone'),
            raw.get('email') or raw.get('Email'),
            raw.get('category') or raw.get('Category'),
        )
        if row is None or not _is_valid_email(row['email']):
            failed += 1
        else:
            rows.append(row)

    return {'rows': rows, 'failed': failed, 'error': None, 'format': 'csv'}


def _parse_txt(file):
    rows   = []
    failed = 0
    try:
        decoded = file.read().decode('utf-8-sig')
        lines   = decoded.splitlines()
    except Exception:
        return {'rows': [], 'failed': 0, 'error': 'Could not read TXT file.', 'format': 'txt'}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split('|')
        if len(parts) < 2:
            failed += 1
            continue
        row = _normalise_row(
            parts[0] if len(parts) > 0 else '',
            parts[1] if len(parts) > 1 else '',
            parts[2] if len(parts) > 2 else '',
            parts[3] if len(parts) > 3 else '',
        )
        if row is None or not _is_valid_email(row['email']):
            failed += 1
        else:
            rows.append(row)

    return {'rows': rows, 'failed': failed, 'error': None, 'format': 'txt'}


def _parse_xlsx(file):
    rows   = []
    failed = 0
    try:
        wb      = openpyxl.load_workbook(file, read_only=True, data_only=True)
        ws      = wb.active
        headers = None
        for i, excel_row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = [str(h).strip().lower() if h else '' for h in excel_row]
                continue
            if not any(excel_row):
                continue

            def cell(col_name, fallback=''):
                if headers and col_name in headers:
                    val = excel_row[headers.index(col_name)]
                    return str(val).strip() if val is not None else fallback
                return fallback

            row = _normalise_row(
                cell('name'),
                cell('phone'),
                cell('email'),
                cell('category'),
            )
            if row is None or not _is_valid_email(row['email']):
                failed += 1
            else:
                rows.append(row)
        wb.close()
    except Exception as e:
        return {'rows': [], 'failed': 0, 'error': f'Could not read XLSX file: {e}', 'format': 'xlsx'}

    return {'rows': rows, 'failed': failed, 'error': None, 'format': 'xlsx'}


def commit_import(user, rows):
    """
    Commits parsed rows to the database.
    Uses the stricter _is_exact_duplicate check — only skips a row if
    both the name AND phone/email already exist together. This means
    'Mum, 08012345678' and 'Mama, 08012345678' will both be imported,
    creating a flaggable duplicate pair for the Settings merge screen.
    """
    imported = 0
    skipped  = 0
    failed   = 0

    for row in rows:
        try:
            if _is_exact_duplicate(user, row['name'], row['phone'], row['email']):
                skipped += 1
                continue
            cat = _get_or_create_category(user, row['category'])
            Contact.objects.create(
                user=user,
                full_name=row['name'],
                phone_number=row['phone'],
                email=row['email'],
                category=cat,
            )
            imported += 1
        except Exception:
            failed += 1

    ImportLog.objects.create(
        user=user,
        imported_count=imported,
        skipped_duplicates=skipped,
        failed_rows=failed,
    )

    return {'imported': imported, 'skipped': skipped, 'failed': failed}


def export_xlsx(user):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Contacts'

    headers = ['Name', 'Phone', 'Email', 'Category', 'Date Added']
    ws.append(headers)

    from openpyxl.styles import Font, PatternFill, Alignment
    header_font  = Font(bold=True, color='FFFFFF')
    header_fill  = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center')

    for col_num, _ in enumerate(headers, 1):
        cell           = ws.cell(row=1, column=col_num)
        cell.font      = header_font
        cell.fill      = header_fill
        cell.alignment = header_align

    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 28
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 18

    contacts = Contact.objects.filter(user=user).select_related('category').order_by('full_name')
    for c in contacts:
        ws.append([
            c.full_name,
            c.phone_number,
            c.email,
            c.category.name if c.category else '',
            c.created_at.strftime('%Y-%m-%d'),
        ])

    return wb


def export_csv(user):
    output   = io.StringIO()
    writer   = csv.writer(output)
    writer.writerow(['name', 'phone', 'email', 'category'])
    contacts = Contact.objects.filter(user=user).select_related('category').order_by('full_name')
    for c in contacts:
        writer.writerow([
            c.full_name,
            c.phone_number,
            c.email,
            c.category.name if c.category else '',
        ])
    return output.getvalue()


def export_txt(user):
    lines    = []
    contacts = Contact.objects.filter(user=user).select_related('category').order_by('full_name')
    for c in contacts:
        lines.append('|'.join([
            c.full_name,
            c.phone_number,
            c.email,
            c.category.name if c.category else '',
        ]))
    return '\n'.join(lines)