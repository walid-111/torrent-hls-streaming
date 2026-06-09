import os
import requests as http_requests
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from .models import User
from .serializers import RegisterSerializer, UserSerializer

FRONTEND = 'http://localhost:3000'


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(
        request,
        username=request.data.get('username'),
        password=request.data.get('password')
    )
    if user:
        login(request, user)
        return Response(UserSerializer(user).data)
    return Response({'error': 'Invalid credentials'}, status=401)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({'message': 'Logged out'})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def profile(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user).data)

    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_detail(request, pk):
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)
    data = UserSerializer(user).data
    data.pop('email')
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def auth_42(request):
    url = (
        'https://api.intra.42.fr/oauth/authorize'
        f'?client_id={os.getenv("FORTYTWO_CLIENT_ID")}'
        f'&redirect_uri={os.getenv("FORTYTWO_REDIRECT_URI")}'
        f'&response_type=code'
    )
    return Response({'url': url})


@api_view(['GET'])
@permission_classes([AllowAny])
def auth_42_callback(request):
    code = request.GET.get('code')
    if not code:
        return redirect(f'{FRONTEND}/login?error=no_code')

    token_res = http_requests.post(
        'https://api.intra.42.fr/oauth/token',
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': os.getenv('FORTYTWO_REDIRECT_URI'),
        },
        auth=(os.getenv('FORTYTWO_CLIENT_ID'), os.getenv('FORTYTWO_CLIENT_SECRET')),
    )
    token = token_res.json().get('access_token')
    if not token:
        return redirect(f'{FRONTEND}/login?error=auth_failed')

    user_data = http_requests.get(
        'https://api.intra.42.fr/v2/me',
        headers={'Authorization': f'Bearer {token}'}
    ).json()

    fortytwo_id = str(user_data['id'])

    user = User.objects.filter(fortytwo_id=fortytwo_id).first()
    if not user:
        base = user_data['login']
        username = base
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base}_{counter}"
            counter += 1

        user = User.objects.create(
            username=username,
            fortytwo_id=fortytwo_id,
            email=user_data.get('email', ''),
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', ''),
        )

    login(request, user)
    return redirect(f'{FRONTEND}/library')


@api_view(['GET'])
@permission_classes([AllowAny])
def auth_github(request):
    url = (
        'https://github.com/login/oauth/authorize'
        f'?client_id={os.getenv("GITHUB_CLIENT_ID")}'
        f'&redirect_uri={os.getenv("GITHUB_REDIRECT_URI")}'
        f'&scope=user:email'
    )
    return Response({'url': url})


@api_view(['GET'])
@permission_classes([AllowAny])
def auth_github_callback(request):
    code = request.GET.get('code')
    if not code:
        return redirect(f'{FRONTEND}/login?error=no_code')

    token_res = http_requests.post(
        'https://github.com/login/oauth/access_token',
        data={
            'client_id': os.getenv('GITHUB_CLIENT_ID'),
            'client_secret': os.getenv('GITHUB_CLIENT_SECRET'),
            'code': code,
        },
        headers={'Accept': 'application/json'}
    )
    token = token_res.json().get('access_token')
    if not token:
        return redirect(f'{FRONTEND}/login?error=auth_failed')

    user_data = http_requests.get(
        'https://api.github.com/user',
        headers={'Authorization': f'Bearer {token}'}
    ).json()

    github_id = str(user_data['id'])

    user = User.objects.filter(github_id=github_id).first()
    if not user:
        email = user_data.get('email') or f"{user_data['login']}@github.local"
        name_parts = (user_data.get('name') or user_data['login']).split(' ', 1)

        base = f"gh_{user_data['login']}"
        username = base
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base}_{counter}"
            counter += 1

        user = User.objects.create(
            username=username,
            github_id=github_id,
            email=email,
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else '',
        )

    login(request, user)
    return redirect(f'{FRONTEND}/library')


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request(request):
    email = request.data.get('email')
    try:
        user = User.objects.get(email=email)
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        reset_url = f"{FRONTEND}/reset-password/confirm?uid={uid}&token={token}"
        send_mail(
            'Reset your password',
            f'Click to reset: {reset_url}',
            os.getenv('EMAIL_HOST_USER'),
            [email],
        )
    except User.DoesNotExist:
        pass
    return Response({'message': 'If email exists, a link has been sent'})


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm(request):
    try:
        uid = force_str(urlsafe_base64_decode(request.data.get('uid')))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError):
        return Response({'error': 'Invalid link'}, status=400)

    if not default_token_generator.check_token(user, request.data.get('token')):
        return Response({'error': 'Expired token'}, status=400)

    user.set_password(request.data.get('new_password'))
    user.save()
    return Response({'message': 'Password reset'})