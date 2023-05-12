from django.urls import path
from .views import *

urlpatterns = [
    path('', Index.as_view(), name='home'),
    path('profile/<slug:username>/', ProfileView.as_view(), name='profile'),
    path('signup', SignUpUser.as_view(), name='signup'),
    path('login', LoginUser.as_view(), name='login'),
    path('bd/', create),
    path('search/', search.as_view(), name='search'),
    path('logout/', LogOutUser, name="logout"),
    path('game/<slug:slug>/', GameView.as_view(), name='game'),
    path('<slug:slug>/', ReviewView.as_view(), name="post_review"),
    path('library/recommendation-list/', RecView.as_view(), name='rec'),
    path('support/send-question/', TechSupportView.as_view(), name='support'),
    path('support/subscribe/', SubscribeView.as_view(), name='subscribe'),
    path('chat/group/', ChatView.as_view(), name="chat"),
    path('pdf/profile/', profilePDF, name='profile-pdf'),
    path('pdf/games/', gamesPDF, name='games-pdf'),
    path('pdf/library/', libraryPDF, name='library-pdf'),
    path('charts/lab5/', ChartView.as_view(), name='charts'),
    path('charts/lab6/', RyadView.as_view(), name='ryad'),
    path('create/user/', CreateUser, name='create-user'),
    path('charts/lab7/', SmoothRyadView.as_view(), name='lab7'),
    path('charts/lab8/', LAB8View.as_view(), name='lab8'),
    path('charts/lab9/', LAB9View.as_view(), name='lab9'),
    path('charts/lab9/dop/', LAB9dopView.as_view(), name='lab9dop'),
    path('charts/lab10/', LAB10View.as_view(), name='lab10'),


]
