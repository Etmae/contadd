from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from .forms import RegisterForm, LoginForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
            )
            messages.success(request, 'Account created successfully. Please sign in.')
            return redirect('login')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.profile.is_admin():
                return redirect('admin_panel')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('login')
    return redirect('dashboard')