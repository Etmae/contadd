from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse, StreamingHttpResponse
from django.db.models import Q, Count
from django.utils import timezone
import io
from datetime import timedelta
from .models import Contact, Category, ImportLog, PendingImport
from .forms import ContactForm
from . import import_export as ie
from django.core.paginator import Paginator


class Echo:
    """File-like adapter used by csv.writer for streaming responses."""

    def write(self, value):
        return value


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
    page_num        = request.GET.get('page', 1)

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

    paginator = Paginator(contacts, 50)
    page      = paginator.get_page(page_num)

    categories       = Category.objects.filter(Q(user=None) | Q(user=user))
    selected_contact = None
    contact_id       = request.GET.get('contact')
    if contact_id:
        selected_contact = get_object_or_404(Contact, id=contact_id, user=user)

    return render(request, 'contacts/contact_list.html', {
        'contacts':         page,
        'categories':       categories,
        'search_query':     search_query,
        'category_filter':  category_filter,
        'sort_by':          sort_by,
        'selected_contact': selected_contact,
        'paginator':        paginator,
        'page':             page,
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
    PendingImport.objects.filter(user=user, created_at__lt=timezone.now() - timedelta(hours=6)).delete()

    if request.method == 'POST' and request.POST.get('action') == 'cancel_import':
        pending_id = request.session.pop('pending_import_id', None)
        if pending_id:
            PendingImport.objects.filter(id=pending_id, user=user).delete()
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
        pending_id = request.session.pop('pending_import_id', None)
        pending = PendingImport.objects.filter(id=pending_id, user=user).first() if pending_id else None
        if not pending:
            messages.error(request, 'Import session expired. Please upload the file again.')
            return redirect('import_export')
        result = ie.commit_import(user, pending.rows)
        pending.delete()
        request.session['import_result'] = result
        return redirect('import_export')

    pending_id = request.session.get('pending_import_id')
    pending = PendingImport.objects.filter(id=pending_id, user=user).first() if pending_id else None
    if pending:
        rows = pending.rows
        
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
            messages.error(request, parsed['error'])
            return redirect('import_export')
        if not parsed['rows']:
            messages.error(request, 'No valid rows found in the file.')
            return redirect('import_export')
        PendingImport.objects.filter(user=user).delete()
        pending = PendingImport.objects.create(user=user, rows=parsed['rows'])
        request.session['pending_import_id'] = pending.id
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
            import csv as csv_module

            writer = csv_module.writer(Echo())
            response = StreamingHttpResponse(
                (writer.writerow(row) for row in ie.export_csv(user)),
                content_type='text/csv'
            )
            response['Content-Disposition'] = 'attachment; filename="contacts.csv"'
            return response
        elif action == 'export_txt':
            response = StreamingHttpResponse(ie.export_txt(user), content_type='text/plain')
            response['Content-Disposition'] = 'attachment; filename="contacts.txt"'
            return response

    return render(request, 'contacts/import_export.html', {
        'import_logs': import_logs,
        'step':        'upload',
    })


def _find_duplicate_groups(user):
    """
    Uses database aggregation to find duplicate phone numbers and emails,
    then fetches only the affected contacts. Runs in O(n) instead of O(n²).
    """
    contacts_qs = Contact.objects.filter(user=user).select_related('category')

    # Find phone numbers that appear more than once for this user
    dup_phones = set(
        contacts_qs
        .values('phone_number')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
        .values_list('phone_number', flat=True)
    )

    # Find emails that appear more than once for this user (exclude blank)
    dup_emails = set(
        contacts_qs
        .exclude(email='')
        .values('email')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
        .values_list('email', flat=True)
    )
    dup_emails_lower = {email.lower() for email in dup_emails}

    # Find names that appear more than once (possible duplicates)
    dup_names = set(
        contacts_qs
        .values('full_name')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
        .values_list('full_name', flat=True)
    )
    dup_names_lower = {name.lower() for name in dup_names}

    # Fetch only the contacts involved in any duplicate
    involved = contacts_qs.filter(
        Q(phone_number__in=dup_phones) |
        Q(email__in=dup_emails) |
        Q(full_name__in=dup_names)
    )

    # Group them in Python — now only iterating over the small duplicate set
    phone_groups = {}
    email_groups = {}
    name_groups  = {}

    for contact in involved.iterator(chunk_size=500):
        if contact.phone_number in dup_phones:
            phone_groups.setdefault(contact.phone_number, []).append(contact)
        elif contact.email and contact.email.lower() in dup_emails_lower:
            email_groups.setdefault(contact.email.lower(), []).append(contact)
        elif contact.full_name.lower() in dup_names_lower:
            name_groups.setdefault(contact.full_name.lower(), []).append(contact)

    groups = []

    for phone, contacts in phone_groups.items():
        if len(contacts) > 1:
            groups.append({
                'contacts':     contacts,
                'match_reason': 'phone',
                'confirmed':    True,
            })

    for email, contacts in email_groups.items():
        if len(contacts) > 1:
            groups.append({
                'contacts':     contacts,
                'match_reason': 'email',
                'confirmed':    True,
            })

    for name, contacts in name_groups.items():
        if len(contacts) > 1:
            groups.append({
                'contacts':     contacts,
                'match_reason': 'name',
                'confirmed':    False,
            })

    return groups

@login_required
def settings_view(request):
    user             = request.user
    duplicate_groups = _find_duplicate_groups(user)
    categories       = Category.objects.filter(Q(user=None) | Q(user=user)).annotate(contact_count=Count('contacts'))
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
    search_query = request.GET.get('q', '').strip()
    user_filter  = request.GET.get('user', '')
    page_num     = request.GET.get('page', 1)

    contacts = Contact.objects.select_related('user', 'category').order_by('-created_at')

    if search_query:
        contacts = contacts.filter(
            Q(full_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    if user_filter:
        contacts = contacts.filter(user_id=user_filter)

    paginator = Paginator(contacts, 50)
    page      = paginator.get_page(page_num)
    all_users = User.objects.only('id', 'username').order_by('username')

    return render(request, 'contacts/admin_contacts.html', {
        'contacts':     page,
        'search_query': search_query,
        'user_filter':  user_filter,
        'all_users':    all_users,
        'paginator':    paginator,
        'page':         page,
    })

@_admin_required
def admin_export_all(request):
    if request.method != 'POST':
        return redirect('admin_panel')

    action = request.POST.get('action')

    if action == 'export_all_xlsx':
        import openpyxl

        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet(title='All Contacts')

        headers = ['Name', 'Phone', 'Email', 'Category', 'Owner', 'Date Added']
        ws.append(headers)

        contacts = Contact.objects.select_related('user', 'category').order_by('user__username', 'full_name')
        for c in contacts.iterator(chunk_size=1000):
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

        writer = csv_module.writer(Echo())

        def rows():
            yield writer.writerow(['name', 'phone', 'email', 'category', 'owner'])
            contacts = Contact.objects.select_related('user', 'category').order_by('user__username', 'full_name')
            for c in contacts.iterator(chunk_size=1000):
                yield writer.writerow([
                    c.full_name,
                    c.phone_number,
                    c.email,
                    c.category.name if c.category else '',
                    c.user.username,
                ])

        response = StreamingHttpResponse(rows(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="all_contacts.csv"'
        return response

    elif action == 'export_all_txt':
        def lines():
            contacts = Contact.objects.select_related('user', 'category').order_by('user__username', 'full_name')
            for c in contacts.iterator(chunk_size=1000):
                yield '|'.join([
                    c.full_name,
                    c.phone_number,
                    c.email,
                    c.category.name if c.category else '',
                    c.user.username,
                ]) + '\n'

        response = StreamingHttpResponse(lines(), content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename="all_contacts.txt"'
        return response

    return redirect('admin_panel')
