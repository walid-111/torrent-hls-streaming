import os
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from users.models import User
from users.serializers import UserSerializer
from movies.models import Movie, Comment


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def users_list(request):
    users = User.objects.all()
    return Response([{'id': u.id, 'username': u.username} for u in users])


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_detail(request, pk):
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        data = {
            'id': user.id,
            'username': user.username,
            'avatar': request.build_absolute_uri(user.avatar.url) if user.avatar else None,
        }
        if request.user.id == user.id:
            data['email'] = user.email
        return Response(data)

    if request.user.id != user.id:
        return Response({'error': 'Forbidden'}, status=403)

    serializer = UserSerializer(user, data=request.data, partial=True)
    if serializer.is_valid():
        if 'password' in request.data:
            user.set_password(request.data['password'])
            user.save()
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def movies_list(request):
    movies = Movie.objects.order_by('-last_watched')[:20]
    return Response([{'id': m.id, 'title': m.title} for m in movies])


@api_view(['GET'])
@permission_classes([AllowAny])
def movie_detail(request, pk):
    try:
        movie = Movie.objects.get(pk=pk)
    except Movie.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    subs = []
    sub_dir = '/app/media/subtitles'
    if os.path.exists(sub_dir):
        for f in os.listdir(sub_dir):
            if f.startswith(movie.title[:50]):
                lang = f.rsplit('_', 1)[-1].replace('.srt', '')
                subs.append(lang)

    return Response({
        'id': movie.id,
        'title': movie.title,
        'rating': movie.rating,
        'year': movie.year,
        'length': movie.length,
        'subtitles': subs,
        'comments_count': movie.comments.count(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def comments_list(request):
    comments = Comment.objects.order_by('-created_at')[:20]
    return Response([{
        'id': c.id,
        'author': c.author.username,
        'content': c.content,
        'created_at': c.created_at,
    } for c in comments])


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def comment_detail(request, pk):
    try:
        comment = Comment.objects.get(pk=pk)
    except Comment.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': comment.id,
            'author': comment.author.username,
            'content': comment.content,
            'created_at': comment.created_at,
        })

    if request.method == 'PATCH':
        comment.content = request.data.get('content', comment.content)
        comment.save()
        return Response({
            'id': comment.id,
            'author': comment.author.username,
            'content': comment.content,
        })

    comment.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def movie_comments(request, movie_id):
    try:
        movie = Movie.objects.get(pk=movie_id)
    except Movie.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        comments = movie.comments.order_by('-created_at')
        return Response([{
            'id': c.id,
            'author': c.author.username,
            'content': c.content,
            'created_at': c.created_at,
        } for c in comments])

    content = request.data.get('content')
    if not content:
        return Response({'error': 'content required'}, status=400)
    comment = Comment.objects.create(movie=movie, author=request.user, content=content)
    return Response({
        'id': comment.id,
        'author': comment.author.username,
        'content': comment.content,
        'created_at': comment.created_at,
    }, status=201)