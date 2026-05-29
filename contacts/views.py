from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Q, Count
import io
from .models import Contact, Category, ImportLog
from .forms import ContactForm
from . import import_export as ie


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home.html')


@login_required
def dashboard(request):
    user             = request.user
    total_contacts   = Contact.objects.filter(user=user).count()
    total_categories = Category.objects.filter(Q(user=None) | Q(user=user)).count()
    recent_contacts  = Contact.objects.filter(user=user).order_by('-created_at')[:5]
    recent_imports   = user.import_logs.all()[:3]
    return render(request, 'contacts/dashboard.html', {
        'total_contacts':   total_contacts,
        'total_categories': total_categories,
        'recent_contacts':  recent_contacts,
        'recent_imports':   recent_imports,
    })


@login_required
def contact_list(request):
    user            = request.user
    contacts        = Contact.objects.filter(user=user)
    search_query    = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '')
    sort_by         = request.GET.get('sort', 'name')

    if search_query:
        contacts = contacts.filter(
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    if category_filter:
        contacts = contacts.filter(category_id=category_filter)
    if sort_by == 'oldest':
        contacts = contacts.order_by('created_at')
    elif sort_by == 'newest':
        contacts = contacts.order_by('-created_at')
    else:
        contacts = contacts.order_by('full_name')

    categories       = Category.objects.filter(Q(user=None) | Q(user=user))
    selected_contact = None
    contact_id       = request.GET.get('contact')
    if contact_id:
        selected_contact = get_object_or_404(Contact, id=contact_id, user=user)

    return render(request, 'contacts/contact_list.html', {
        'contacts':         contacts,
        'categories':       categories,
        'search_query':     search_query,
        'category_filter':  category_filter,
        'sort_by':          sort_by,
        'selected_contact': selected_contact,
    })


def _check_duplicate(user, phone_number, email, exclude_id=None):
    qs = Contact.objects.filter(user=user)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    if phone_number and qs.filter(phone_number=phone_number).exists():
        return qs.filter(phone_number=phone_number).first()
    if email and qs.filter(email=email).exists():
        return qs.filter(email=email).first()
    return None


@login_required
def add_contact(request):
    if request.method == 'POST':
        form = ContactForm(request.user, request.POST, request.FILES)
        if form.is_valid():
            phone     = form.cleaned_data['phone_number']
            email     = form.cleaned_data.get('email', '')
            duplicate = _check_duplicate(request.user, phone, email)
            if duplicate:
                messages.error(request, f'A contact with this phone or email already exists: {duplicate.full_name}')
                return render(request, 'contacts/add_contact.html', {'form': form})
            contact      = form.save(commit=False)
            contact.user = request.user
            contact.save()
            messages.success(request, f'{contact.full_name} added successfully.')
            return redirect(f'/contacts/?contact={contact.id}')
    else:
        form = ContactForm(request.user)
    return render(request, 'contacts/add_contact.html', {'form': form})


@login_required
def edit_contact(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id, user=request.user)
    if request.method == 'POST':
        form = ContactForm(request.user, request.POST, request.FILES, instance=contact)
        if form.is_valid():
            phone     = form.cleaned_data['phone_number']
            email     = form.cleaned_data.get('email', '')
            duplicate = _check_duplicate(request.user, phone, email, exclude_id=contact.id)
            if duplicate:
                messages.error(request, f'Another contact with this phone or email already exists: {duplicate.full_name}')
                return render(request, 'contacts/edit_contact.html', {'form': form, 'contact': contact})
            form.save()
            messages.success(request, f'{contact.full_name} updated successfully.')
            return redirect(f'/contacts/?contact={contact.id}')
    else:
        form = ContactForm(request.user, instance=contact)
    return render(request, 'contacts/edit_contact.html', {'form': form, 'contact': contact})


@login_required
def delete_contact(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id, user=request.user)
    if request.method == 'POST':
        name = contact.full_name
        contact.delete()
        messages.success(request, f'{name} deleted.')
        return redirect('contact_list')
    return render(request, 'contacts/delete_contact.html', {'contact': contact})


@login_required
def import_export(request):
    user        = request.user
    import_logs = user.import_logs.all()[:10]

    if request.method == 'POST' and request.POST.get('action') == 'cancel_import':
        request.session.pop('import_preview_rows', None)
        request.session.pop('import_result',       None)
        return redirect('import_export')

    if request.method == 'POST' and request.POST.get('action') == 'done_import':
        request.session.pop('import_result', None)
        return redirect('import_export')

    if 'import_result' in request.session:
        result = request.session['import_result']
        return render(request, 'contacts/import_export.html', {
            'step':        'success',
            'result':      result,
            'import_logs': import_logs,
        })

    if request.method == 'POST' and request.POST.get('action') == 'confirm_import':
        rows = request.session.pop('import_preview_rows', None)
        if not rows:
            messages.error(request, 'Import session expired. Please upload the file again.')
            return redirect('import_export')
        result = ie.commit_import(user, rows)
        request.session['import_result'] = result
        return redirect('import_export')

    if 'import_preview_rows' in request.session:
        rows = request.session['import_preview_rows']
        
        # OPTIMIZATION: Extract match signatures up front into highly optimized memory sets
        uploaded_phones = {str(r['phone']).strip() for r in rows if r.get('phone')}
        uploaded_emails = {str(r['email']).strip().lower() for r in rows if r.get('email')}
        
        existing_contacts = Contact.objects.filter(user=user)
        existing_phones = set(existing_contacts.filter(phone_number__in=uploaded_phones).values_list('phone_number', flat=True))
        existing_emails = set(existing_contacts.filter(email__in=uploaded_emails).values_list('email', flat=True))
        
        # Light in-memory iteration completely bypassing database round-trips inside the loop
        duplicate_count = sum(
            1 for r in rows
            if (str(r.get('phone')).strip() in existing_phones) or (str(r.get('email')).strip().lower() in existing_emails)
        )
        
        new_count = len(rows) - duplicate_count
        return render(request, 'contacts/import_export.html', {
            'step':            'preview',
            'preview_rows':    rows[:10],
            'total_rows':      len(rows),
            'new_count':       new_count,
            'duplicate_count': duplicate_count,
            'import_logs':     import_logs,
        })

    if request.method == 'POST' and request.POST.get('action') == 'upload':
        uploaded = request.FILES.get('file')
        if not uploaded:
            messages.error(request, 'Please select a file to import.')
            return redirect('import_export')
        parsed = ie.parse_file_for_preview(uploaded, uploaded.name)
        if parsed['error']:
            messages.error(parsed['error'])
            return redirect('import_export')
        if not parsed['rows']:
            messages.error(request, 'No valid rows found in the file.')
            return redirect('import_export')
        request.session['import_preview_rows'] = parsed['rows']
        return redirect('import_export')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'export_xlsx':
            wb     = ie.export_xlsx(user)
            buffer = io.BytesIO()
            wb.save(buffer)
            buffer.seek(0)
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="contacts.xlsx"'
            return response
        elif action == 'export_csv':
            content  = ie.export_csv(user)
            response = HttpResponse(content, content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="contacts.csv"'
            return response
        elif action == 'export_txt':
            content  = ie.export_txt(user)
            response = HttpResponse(content, content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="contacts.txt"'
            return response

    return render(request, 'contacts/import_export.html', {
        'import_logs': import_logs,
        'step':        'upload',
    })


def _find_duplicate_groups(user):
    # Optimize fields fetched to keep memory footprints low
    contacts = list(Contact.objects.filter(user=user).select_related('category').only(
        'id', 'phone_number', 'email', 'full_name', 'category__name'
    ))
    visited  = set()
    groups   = []

    # Map lookups via hash maps for swift tracking overhead
    for i, contact in enumerate(contacts):
        if contact.id in visited:
            continue
        group        = [contact]
        match_reason = None
        confirmed    = False

        c_phone = contact.phone_number
        c_email = contact.email.strip().lower() if contact.email else None
        c_name  = contact.full_name.strip().lower()

        for other in contacts[i+1:]:
            if other.id in visited:
                continue
                
            phone_match = c_phone and other.phone_number and (c_phone == other.phone_number)
            email_match = c_email and other.email and (c_email == other.email.strip().lower())
            name_match  = c_name == other.full_name.strip().lower()

            if phone_match or email_match or name_match:
                group.append(other)
                visited.add(other.id)
                if phone_match:
                    match_reason = 'phone'
                    confirmed    = True
                elif email_match:
                    match_reason = 'email'
                    confirmed    = True
                elif name_match and not match_reason:
                    match_reason = 'name'

        if len(group) > 1:
            visited.add(contact.id)
            groups.append({
                'contacts':     group,
                'match_reason': match_reason,
                'confirmed':    confirmed,
            })

    return groups


@login_required
def settings_view(request):
    user             = request.user
    duplicate_groups = _find_duplicate_groups(user)
    categories       = Category.objects.filter(Q(user=None) | Q(user=user))
    total_contacts   = Contact.objects.filter(user=user).count()
    confirmed_count  = sum(1 for g in duplicate_groups if g['confirmed'])
    possible_count   = sum(1 for g in duplicate_groups if not g['confirmed'])

    return render(request, 'contacts/settings.html', {
        'duplicate_groups': duplicate_groups,
        'duplicate_count':  len(duplicate_groups),
        'confirmed_count':  confirmed_count,
        'possible_count':   possible_count,
        'categories':       categories,
        'total_contacts':   total_contacts,
    })


@login_required
def merge_contacts(request):
    if request.method != 'POST':
        return redirect('settings')

    primary_id    = request.POST.get('primary_id')
    duplicate_ids = request.POST.getlist('duplicate_ids')

    if not primary_id or not duplicate_ids:
        messages.error(request, 'Invalid merge request.')
        return redirect('settings')

    primary = get_object_or_404(Contact, id=primary_id, user=request.user)
    deleted = 0

    for dup_id in duplicate_ids:
        if str(dup_id) == str(primary_id):
            continue
        dup = Contact.objects.filter(id=dup_id, user=request.user).first()
        if not dup:
            continue
        if not primary.email and dup.email:
            primary.email = dup.email
        if not primary.category and dup.category:
            primary.category = dup.category
        if not primary.image and dup.image:
            primary.image = dup.image
        dup.delete()
        deleted += 1

    primary.save()
    messages.success(
        request,
        f'Merged {deleted} duplicate{"s" if deleted != 1 else ""} into {primary.full_name}.'
    )
    return redirect('settings')


@login_required
def dismiss_duplicates(request):
    if request.method != 'POST':
        return redirect('settings')
    messages.success(request, 'Duplicate group dismissed.')
    return redirect('settings')


@login_required
def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id, user=request.user)
    if request.method == 'POST':
        name = category.name
        category.delete()
        messages.success(request, f'Category "{name}" deleted.')
    return redirect('settings')


@login_required
def add_category(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Category name cannot be empty.')
            return redirect('settings')
        exists = Category.objects.filter(
            Q(user=None) | Q(user=request.user),
            name__iexact=name
        ).exists()
        if exists:
            messages.error(request, f'Category "{name}" already exists.')
            return redirect('settings')
        Category.objects.create(user=request.user, name=name)
        messages.success(request, f'Category "{name}" created.')
    return redirect('settings')


# ── Admin views ───────────────────────────────────────────────────────────────

def _admin_required(view_func):
    """Decorator that combines login_required with admin role check."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.profile.is_admin():
            messages.error(request, 'You do not have permission to access the admin panel.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@_admin_required
def admin_panel(request):
    total_users    = User.objects.count()
    total_contacts = Contact.objects.count()
    total_cats     = Category.objects.count()
    recent_users   = User.objects.order_by('-date_joined')[:5]

    top_users = (
        User.objects
        .annotate(contact_count=Count('contacts'))
        .order_by('-contact_count')[:5]
    )

    recent_contacts = Contact.objects.select_related('user', 'category').order_by('-created_at')[:10]

    return render(request, 'contacts/admin_panel.html', {
        'total_users':      total_users,
        'total_contacts':   total_contacts,
        'total_cats':       total_cats,
        'recent_users':     recent_users,
        'top_users':        top_users,
        'recent_contacts':  recent_contacts,
    })


@_admin_required
def admin_users(request):
    search_query = request.GET.get('q', '').strip()
    users        = User.objects.annotate(contact_count=Count('contacts')).order_by('-date_joined')

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    return render(request, 'contacts/admin_users.html', {
        'users':        users,
        'search_query': search_query,
    })


@_admin_required
def admin_toggle_user(request, user_id):
    if request.method != 'POST':
        return redirect('admin_users')

    if str(user_id) == str(request.user.id):
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('admin_users')

    target = get_object_or_404(User, id=user_id)
    target.is_active = not target.is_active
    target.save()

    status = 'activated' if target.is_active else 'deactivated'
    messages.success(request, f'{target.username} has been {status}.')
    return redirect('admin_users')


@_admin_required
def admin_contacts(request):
    search_query    = request.GET.get('q', '').strip()
    user_filter     = request.GET.get('user', '')
    contacts        = Contact.objects.select_related('user', 'category').order_by('-created_at')

    if search_query:
        contacts = contacts.filter(
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    if user_filter:
        contacts = contacts.filter(user_id=user_filter)

    all_users = User.objects.all().order_by('username')

    return render(request, 'contacts/admin_contacts.html', {
        'contacts':     contacts,
        'search_query': search_query,
        'user_filter':  user_filter,
        'all_users':    all_users,
    })


@_admin_required
def admin_export_all(request):
    if request.method != 'POST':
        return redirect('admin_panel')

    action = request.POST.get('action')

    if action == 'export_all_xlsx':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'All Contacts'

        headers = ['Name', 'Phone', 'Email', 'Category', 'Owner', 'Date Added']
        ws.append(headers)

        header_font  = Font(bold=True, color='FFFFFF')
        header_fill  = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
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
        ws.column_dimensions['F'].width = 15

        contacts = Contact.objects.select_related('user', 'category').order_by('user__username', 'full_name')
        for c in contacts:
            ws.append([
                c.full_name,
                c.phone_number,
                c.email,
                c.category.name if c.category else '',
                c.user.username,
                c.created_at.strftime('%Y-%m-%d'),
            ])

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="all_contacts.xlsx"'
        return response

    elif action == 'export_all_csv':
        import csv as csv_module
        output = io.StringIO()
        writer = csv_module.writer(output)
        writer.writerow(['name', 'phone', 'email', 'category', 'owner'])
        contacts = Contact.objects.select_related('user', 'category').order_by('user__username', 'full_name')
        for c in contacts:
            writer.writerow([
                c.full_name,
                c.phone_number,
                c.email,
                c.category.name if c.category else '',
                c.user.username,
            ])
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="all_contacts.csv"'
        return response

    return redirect('admin_panel')