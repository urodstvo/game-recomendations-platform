import os
import random
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import Any, Dict
import locale

locale.setlocale(locale.LC_ALL, "ru_RU")  # russian

import requests
from django.contrib.auth import logout, login
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render, redirect
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, CreateView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from sklearn.cluster import KMeans
import time
from .utils import *
from .models import *
from .forms import *
import multiprocessing
from fill_db import get_similar
from rec_func import analyze_comment
import math
import pandas as pd
from django_pandas.io import read_frame

from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string, get_template
from django.conf import settings

import pdfkit as pdf


def LogOutUser(request):
    logout(request)
    return redirect('home')


class Index(ListView):
    model = Game
    template_name = 'game_app/index.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['popular'] = Game.objects.filter(
            rating_count__gt=0).order_by('-rating_count', '-release_date')[:6]
        context['recently'] = Game.objects.filter(release_date__lte=datetime.now()).order_by('-release_date')[:6]
        context['waiting'] = Game.objects.filter(release_date__gt=datetime.now()).order_by('-release_date').order_by(
            'release_date')[:5]
        return context

    def get_success_url(self):
        return reverse_lazy('home')


class GameView(DetailView):
    model = Game
    template_name = 'game_app/game.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    @staticmethod
    def get_similar_games():
        data = pd.DataFrame(Game.objects.values())
        data = data[:300]
        kmeans = KMeans(n_clusters=4, random_state=42)
        kmeans.fit(data)
        data['label'] = kmeans.labels_
        return data["label"].query("label == 1").head(10)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context["similar"] = self.get_similar(self.object.game_id)
        context['back_img'] = Images.objects.filter(game_id=self.object.game_id)[1]
        context['websites'] = Websites.objects.filter(game_id=self.object.game_id)
        context['images'] = Images.objects.filter(game_id=self.object.game_id)[1:]
        context['videos'] = Videos.objects.filter(game_id=self.object.game_id)
        try:
            context['prev'] = Library.objects.get(user=self.request.user, game=self.object)
        except:
            pass
        context["reviews"] = Reviews.objects.filter(game=self.object).order_by("-date")[:5]
        return context

    @staticmethod
    def get_similar(game_id):
        games = get_similar(game_id)
        return Game.objects.filter(game_id__in=games)


class ProfileView(DetailView):
    model = User
    template_name = 'game_app/profile.html'
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def post(self, request, username):
        profile_bd = Profile.objects.get(user=request.user)
        profile = ProfileForm(self.request.POST, request.FILES, instance=request.user.profile,
                              initial={'nickname': profile_bd.nickname, 'avatar': profile_bd.avatar})
        if profile.is_valid():
            profile.save()
        return redirect('profile', username)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = Profile.objects.get(user=context['object'])
        context['library'] = Library.objects.filter(user=context['object'])
        context['game_count'] = len(list(Library.objects.filter(user=context['object'])))
        context['review_count'] = len(list(Library.objects.filter(user=context['object'], review__isnull=False)))
        context['rate_count'] = len(list(Library.objects.filter(user=context['object'], rate__isnull=False)))
        context['rates'] = [len(list(Library.objects.filter(user=context['object'], rate=i))) for i in range(1, 11)]
        pc = 0
        ps = 0
        android = 0
        ios = 0
        linux = 0
        sega = 0
        xbox = 0
        nintendo = 0
        total = 0
        for game in Library.objects.filter(user=context['object']):
            for plat in game.game.platforms.all():
                if 'PC' in plat.name:
                    pc += 1
                if 'Linux' in plat.name:
                    linux += 1
                if 'Play' in plat.name:
                    ps += 1
                if 'Android' in plat.name:
                    android += 1
                if 'iOS' in plat.name:
                    ios += 1
                if 'Nintendo' in plat.name:
                    nintendo += 1
                if 'Sega' in plat.name:
                    sega += 1
                if 'Xbox' in plat.name:
                    xbox += 1
                total += 1
        if total > 0:
            context['pc_count'] = pc / total
            context['ps_count'] = ps / total
            context['ios_count'] = ios / total
            context['android_count'] = android / total
            context['linux_count'] = linux / total
            context['sega_count'] = sega / total
            context['nintendo_count'] = nintendo / total
            context['xbox_count'] = xbox / total
        # print(context['nintendo_count'], context['xbox_count'])
        context['settings_form'] = ProfileForm

        # print(self.template_name)
        # t = render_to_string(self.template_name, context)
        # pdf.from_string(t, '../media/profile.pdf', css=css)
        # pdf.from_url('http://127.0.0.1:8000/profile/admin/', '../media/profile.pdf')

        return context


def profilePDF(request):
    # The name of your PDF file
    filename = 'filename.pdf'

    # HTML FIle to be converted to PDF - inside your Django directory
    template = get_template('game_app/profile_pdf.html')

    # Add any context variables you need to be dynamically rendered in the HTML
    try:
        user = User.objects.get(username=request.GET.get('user'))
        context = {}
        context['user'] = user
        context['library'] = Library.objects.filter(user=user)
        context['game_count'] = len(Library.objects.filter(user=user))
        context['review_count'] = len(list(Library.objects.filter(user=user, review__isnull=False)))
        context['rate_count'] = len(list(Library.objects.filter(user=user, rate__isnull=False)))
        context['rates'] = []
        for i in range(1, 11):
            context['rates'].append({"rate": i,
                                     "count": len(list(Library.objects.filter(user=user, rate=i))),
                                     "games": Library.objects.filter(user=user, rate=i)})
        context['ratio'] = {}
        pc = 0
        ps = 0
        android = 0
        ios = 0
        linux = 0
        sega = 0
        xbox = 0
        nintendo = 0
        total = 0
        for game in context['library']:
            for plat in game.game.platforms.all():
                if 'PC' in plat.name:
                    pc += 1
                if 'Linux' in plat.name:
                    linux += 1
                if 'Play' in plat.name:
                    ps += 1
                if 'Android' in plat.name:
                    android += 1
                if 'iOS' in plat.name:
                    ios += 1
                if 'Nintendo' in plat.name:
                    nintendo += 1
                if 'Sega' in plat.name:
                    sega += 1
                if 'Xbox' in plat.name:
                    xbox += 1
                total += 1
        if total > 0:
            context['ratio'] = {'pc': pc,
                                "ps": ps,
                                "ios": ios,
                                "android": android,
                                "linux": linux,
                                "sega": sega,
                                "nintendo": nintendo,
                                "xbox": xbox}
            context['total'] = total

        # Render the HTML
        html = template.render(context)

        # Options - Very Important [Don't forget this]
        options = {
            'encoding': 'UTF-8',
            'javascript-delay': '1000',  # Optional
            'enable-local-file-access': None,  # To be able to access CSS
            'page-size': 'A4',
            'custom-header': [
                ('Accept-Encoding', 'gzip')
            ],
        }
        # Javascript delay is optional

        # IF you have CSS to add to template
        css = os.path.join(settings.STATIC_ROOT, 'game_app', 'css', 'pdf.css')
        # css2 = os.path.join(settings.STATIC_ROOT, 'css', 'bootstrap.css')

        # Create the file
        file_content = pdf.from_string(html, False, options=options, css=css)

        # Create the HTTP Response
        response = HttpResponse(file_content, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename = {}'.format(filename)
    except:
        response = HttpResponseNotFound("No such user")
    # Return
    return response


def gamesPDF(request):
    # The name of your PDF file
    filename = 'filename.pdf'

    # HTML FIle to be converted to PDF - inside your Django directory
    template = get_template('game_app/games_pdf.html')

    # Add any context variables you need to be dynamically rendered in the HTML
    try:
        context = {}
        context['games'] = Game.objects.filter(pk__in=request.session['games'])
        context['prices'] = []
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                 'Chrome/108.0.0.0 Safari/537.36',
                   'Accept-language': 'ru-RU,ru;q=0.9,be;q=0.8,el;q=0.7,'
                                      'en;q=0.6', 'Accept': r'*/*'}
        sum = 0
        for game in context['games']:
            try:
                site = Websites.objects.get(game_id=game.pk, name='steam')
                id = site.url[35:]
                r = requests.get(
                    url=f'https://store.steampowered.com/api/appdetails?filters=price_overview&appids={id}',
                    headers=headers).json()
                data = r[id]
                if data["success"]:
                    context['prices'].append(data["data"]["price_overview"]["final_formatted"])
                    sum += int(data["data"]["price_overview"]["final_formatted"].split(' ')[0])
                else:
                    context['prices'].append('Недоступна')
            except:
                context['prices'].append('-')
        context['sum'] = sum
        context['table'] = {}
        for i in range(len(context['prices'])):
            context['table'] |= {list(context['games'])[i]: context['prices'][i]}
        # print(context['table'])
        # Render the HTML
        html = template.render(context)

        # Options - Very Important [Don't forget this]
        options = {
            'encoding': 'UTF-8',
            'javascript-delay': '1000',  # Optional
            'enable-local-file-access': None,  # To be able to access CSS
            'page-size': 'A4',
            'custom-header': [
                ('Accept-Encoding', 'gzip')
            ],
        }
        # Javascript delay is optional

        # IF you have CSS to add to template
        css = os.path.join(settings.STATIC_ROOT, 'game_app', 'css', 'pdf.css')
        # css2 = os.path.join(settings.STATIC_ROOT, 'css', 'bootstrap.css')

        # Create the file
        file_content = pdf.from_string(html, False, options=options, css=css)

        # Create the HTTP Response
        response = HttpResponse(file_content, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename = {}'.format(filename)
    except:
        response = HttpResponseNotFound("wrong request")
    # Return
    return response


def libraryPDF(request):
    # The name of your PDF file
    filename = 'filename.pdf'

    # HTML FIle to be converted to PDF - inside your Django directory
    template = get_template('game_app/library_pdf.html')

    # Add any context variables you need to be dynamically rendered in the HTML
    try:
        context = {}
        user = User.objects.get(username=request.POST.get('user'))
        start = request.POST.get('start', 0)
        if start:
            start = start.split('-')
            start = date(int(start[0]), int(start[1]), 1)
        else:
            start = user.date_joined
            start = date(start.year, start.month, 1)

        context['start'] = start

        end = Library.objects.filter(user=user).order_by('-added_at')[0].added_at
        end = request.POST.get('end', 0)
        if end:
            end = end.split('-')
            end = date(int(end[0]), int(end[1]) + 1, 1)
        else:
            end = Library.objects.filter(user=user).order_by('-added_at')[0].added_at
            end = date(end.year, end.month + 1, 1)
        context['end'] = end
        context['user'] = user
        context['total'] = 0
        context['data'] = []
        while start < end:
            try:
                games = Library.objects.filter(user=user, added_at__gte=start,
                                               added_at__lt=start + relativedelta(months=1))
                games = [game.game.name for game in games.all()]
                context['total'] += len(games)
                stat = {'games': games,
                        'count': len(list(games))}
                context['data'].append({'year': start.year, 'month': start.strftime('%B'), **stat})
            except:
                pass
            start += relativedelta(months=1)
        # print(context['data'])
        html = template.render(context)

        # Options - Very Important [Don't forget this]
        options = {
            'encoding': 'UTF-8',
            'javascript-delay': '1000',  # Optional
            'enable-local-file-access': None,  # To be able to access CSS
            'page-size': 'A4',
            'custom-header': [
                ('Accept-Encoding', 'gzip')
            ],
        }
        # Javascript delay is optional

        # IF you have CSS to add to template
        css = os.path.join(settings.STATIC_ROOT, 'game_app', 'css', 'pdf.css')
        # css2 = os.path.join(settings.STATIC_ROOT, 'css', 'bootstrap.css')

        # Create the file
        file_content = pdf.from_string(html, False, options=options, css=css)

        # Create the HTTP Response
        response = HttpResponse(file_content, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename = {}'.format(filename)
    except:
        response = HttpResponseNotFound("wrong request")
    # Return
    return response


class LoginUser(DataMixin, LoginView):
    form_class = AuthenticationForm
    template_name = 'game_app/login.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context()
        return dict(list(context.items()) + list(c_def.items()))

    def get_success_url(self):
        return reverse_lazy('home')


class SignUpUser(DataMixin, CreateView):
    form_class = UserCreationForm
    template_name = 'game_app/register.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context()
        return dict(list(context.items()) + list(c_def.items()))

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        return redirect('home')


class search(ListView):
    # model = Game
    template_name = 'game_app/search.html'
    paginate_by = 50

    def get_queryset(self):
        rate = self.request.GET.get('rate')
        alp_asc = self.request.GET.get('alp_asc')
        name = self.request.GET.get('name')
        start = self.request.GET.get('start')
        end = self.request.GET.get('end')
        if end and start and end < start:
            start, end = end, start
        genres = self.request.GET.get('genres').split(',')[:-1] if self.request.GET.get('genres') else []
        genres = Genres.objects.filter(name__in=genres)
        platforms = self.request.GET.get('platforms').split(',')[:-1] if self.request.GET.get('platforms') else []
        platforms = Platforms.objects.filter(name__in=platforms)
        developers = self.request.GET.get('developers').split(',')[:-1] if self.request.GET.get('developers') else []
        game = Game.objects.none()
        if name is not None:
            if alp_asc == 'False':
                if rate:
                    game = Game.objects.filter(name__icontains=name).order_by(Lower('name').desc()).order_by('rating')
                else:
                    game = Game.objects.filter(name__icontains=name).order_by(Lower('name').desc()).order_by('-rating')
            else:
                if rate:
                    game = Game.objects.filter(name__icontains=name).order_by(Lower('name').asc()).order_by('rating')
                else:
                    game = Game.objects.filter(name__icontains=name).order_by(Lower('name').asc()).order_by('-rating')

            if start:
                game = game.exclude(Q(release_date__lt=start) | Q(release_date__isnull=True))
            if end:
                game = game.exclude(Q(release_date__gt=end) | Q(release_date__isnull=True))
            if list(genres):
                for i in list(genres):
                    game = game.exclude(~Q(genres=i))
            if list(platforms):
                for i in list(platforms):
                    game = game.exclude(~Q(platforms=i))
            if developers:
                for i in developers:
                    game = game.exclude(~Q(developer=i))
        self.request.session['games'] = [i.pk for i in game]
        return game

    def get_context_data(self, *, object_list=None, **kwargs):
        text = self.request.GET.get('name')
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get('page', '1')
        context['page_range'] = context['paginator'].get_elided_page_range(number=page, on_ends=1, on_each_side=1)
        context['get_req'] = self.request.GET
        context['genres'] = Genres.objects.all()
        context['platforms'] = Platforms.objects.all()
        context['developers'] = Game.objects.values('developer').distinct().order_by('developer')

        return context


def create(request):
    offset = 107655
    while offset < 230_000:
        i = 0
        games = get_game(offset)
        try:
            for game in games:
                print(game["game_id"])
                i += 1  # 1
                # for j in game:
                #     print(j, ' : ', game[j])
                i += 1  # 2
                new_game = Game(game_id=game["game_id"], name=game["name"], slug=game["slug"],
                                developer=game["developer"],
                                description=game["description"], rating=int(game["rating"]),
                                rating_count=int(game["rating_count"]))
                if game["cover"]:
                    new_game.cover = game["cover"]
                if game["release_date"]:
                    new_game.release_date = game["release_date"]
                new_game.save()
                i += 1  # 3
                new_game.genres.set(Genres.objects.filter(name__in=game["genres"]))
                i += 1  # 4
                new_game.platforms.set(Platforms.objects.filter(name__in=game["platforms"]))
                i += 1  # 5
                new_game.save()
                i += 1  # 6
                if len(game["websites"]) > 0:
                    for el in game["websites"]:
                        if len(list(Websites.objects.filter(game_id=game["game_id"], name=el,
                                                            url=game["websites"][el]))) == 0:
                            Websites(game_id=game["game_id"], name=el, url=game["websites"][el]).save()
                i += 1  # 7
                if len(game["release_dates"]) > 0:
                    for el in game["release_dates"]:
                        if len(list(ReleaseDates.objects.filter(game_id=game["game_id"], platform=el))) == 0:
                            rel_date = ReleaseDates(game_id=game["game_id"], platform=el)
                            if game["release_dates"][el]:
                                rel_date.date = game["release_dates"][el]
                            rel_date.save()
                i += 1  # 8
                if len(game["video"]) > 0:
                    for el in game["video"]:
                        if len(list(Videos.objects.filter(game_id=game["game_id"], video_id=el))) == 0:
                            Videos(game_id=game["game_id"], video_id=el).save()
                i += 1  # 9
                if len(game["images"]) > 0:
                    for el in game["images"]:
                        if len(list(Images.objects.filter(game_id=game["game_id"], image_id=el))) == 0:
                            Images(game_id=game["game_id"], image_id=el).save()
                i = 0
                print('end')
        except:
            print('error', i)
            i = 0
            break
        else:
            offset += 500

    context = {}
    return render(request, 'game_app/bd.html', context=context)


class ReviewView(View):
    def post(self, request, slug):
        game = Game.objects.get(slug=slug)
        text = request.POST.get('text')
        rate = request.POST.get('rate', None)

        try:
            review = Reviews.objects.get(game=game, user=request.user)
            # print('get suc')
            review.text = text
            # print('update suc')
            review.save()
        except:
            review = Reviews()
            review.game = game
            review.text = text
            review.user = request.user
            review.save()

        try:
            library = Library.objects.get(user=request.user, game=game)
            library.review = review
            if rate:
                library.rate = rate
            library.save()
        except:
            library = Library()
            library.game = game
            library.user = request.user
            library.review = review
            if rate:
                library.rate = rate
            library.save()

        return redirect("game", slug)


class RecView(ListView):
    template_name = 'game_app/recommendation.html'

    @staticmethod
    def get_format_dict(arr):
        mentions = dict()
        for el in arr:
            if el.user not in mentions:
                mentions[el.user] = dict()
            if el.rate is not None:
                mentions[el.user][el.game] = el.rate
            else:
                mentions[el.user][el.game] = 5
        return mentions

    @staticmethod
    def distCosine(vecA, vecB):
        print(vecA)

        def dotProduct(vecA, vecB):
            d = 0.0
            for dim in vecA:
                if dim in vecB:
                    d += vecA[dim] * vecB[dim]
            return d

        return dotProduct(vecA, vecB) / math.sqrt(dotProduct(vecA, vecA)) \
               / math.sqrt(dotProduct(vecB, vecB))

    @classmethod
    def makeMatches(self, userID, userRates, nBestUsers, nBestProducts):
        matches = [(u, self.distCosine(userRates[userID], userRates[u])) for u in userRates if u != userID]
        print(userRates)
        bestMatches = sorted(matches, key=lambda x: x[1], reverse=True)[:nBestUsers]

        sim = dict()
        sim_all = sum([x[1] for x in bestMatches])
        bestMatches = dict([x for x in bestMatches if x[1] > 0.0])
        # print(bestMatches) #users
        for relatedUser in bestMatches:
            for product in userRates[relatedUser]:
                if product not in userRates[userID]:
                    if product not in sim:
                        sim[product] = 0.0
                    sim[product] += userRates[relatedUser][product] * bestMatches[relatedUser]
        for product in sim:
            sim[product] /= sim_all
        bestProducts = sorted(sim.items(), key=lambda x: x[1], reverse=True)[:nBestProducts]  # games
        # return [(x[0], x[1]) for x in bestProducts]
        return {'games': [x[0] for x in bestProducts], 'users': [x for x in bestMatches]}

    @classmethod
    def makeRecommendations(self, matches):
        rec_list = {'users': [], "games": [], 'coefs': []}
        urls = []
        games = []
        no_url_games = []
        for game in matches['games']:
            try:
                urls.append(Websites.objects.get(game_id=game.game_id, name='steam').url)
                games.append(game)
            except:
                no_url_games.append(game.game_id)

        probas = analyze_comment(urls)
        for index in range(len(probas)):
            rec_list["games"].append(games[index].game_id)
            rec_list["coefs"].append(probas[index])

        rec_list['games'] += no_url_games
        for user in matches["users"]:
            rec_list["users"].append(user.username)
        return rec_list

    def get_queryset(self):
        return Library.objects.all()

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        games = self.request.session.get('games', 0)
        if not games:
            recs = self.makeRecommendations(
                self.makeMatches(self.request.user, self.get_format_dict(self.object_list), 20, 20))
            context['games'] = Game.objects.filter(game_id__in=recs["games"])
            context['users'] = User.objects.filter(username__in=recs["users"])
            self.request.session['games'] = [i.pk for i in context['games']]
            self.request.session['users'] = [i.pk for i in context['users']]
        else:
            context['games'] = Game.objects.filter(pk__in=self.request.session['games'])
            context['users'] = User.objects.filter(pk__in=self.request.session['users'])

        # text = '''<p><span>РЕКОМЕНДОВАНЫЕ ИГРЫ</span>, СОСТАВЛЕННЫЕ ПО ВАШЕЙ ЛИЧНОЙ БИБЛИОТЕКЕ ИГР.</p>
        #             <p>В РАСЧЁТЕ УЧАВСТВОВАЛИ <span>ПОЛЬЗОВАТЕЛИ</span>, С КОТОРЫМИ У ВАС СХОЖИ ИНТЕРЕСЫ.</p>
        #             <p>ПРИ ЭТОМ УЧИТЫВАЛИСЬ <span>ОТЗЫВЫ</span> НА КАЖДУЮ ИГРУ.</p>
        #             <p>НАДЕЕМСЯ, ЧТО ВЫ ДОВОЛЬНЫ РЕКОМЕНДАЦИЯМИ</p>'''
        # for index in range(len(context['games'])):
        #     if index < len(recs['coefs']):
        #         text += f'<b>{context["games"][index].name}</b>:\tанализ отзывов на эту дал оценку - \t<b>{recs["coefs"][index] * 100 // 1}%</b> негативных сообщений;<br><br> '
        #     else:
        #         text += f'<b>{context["games"][index].name}</b>:\tанализ отзывов не проводился(Отзывы недоступны) <br><br>'
        # send(self.request.user.email, text)
        return context


def send(email, text):
    data = {
        'topic': f'Ваш список рекомендаций',
        'text': text,
        'user': 'Сайт',
    }
    html_body = render_to_string('game_app/email_template.html', data)
    msg = EmailMultiAlternatives(data['topic'], html_body, from_email=settings.EMAIL_HOST_USER,
                                 to=[email, ])
    msg.content_subtype = "html"
    msg.send()
    # print('email done')


class TechSupportView(View):
    def get(self, request):
        topics = MessageTopics.objects.all()
        selected = []
        for topic in topics:
            if request.user in topic.users.all():
                selected.append(topic)
        context = {'topics': topics, 'selected': selected}
        return render(request, template_name='game_app/TechSupport.html', context=context)

    def post(self, request):
        if request.POST.get('topic') and request.POST.get('text'):
            data = {
                'topic': request.POST.get('topic'),
                'text': request.POST.get('text'),
                'user': request.user.email,
            }
            message = TechSupport()
            message.question = data['text']
            message.user = request.user
            message.save()
            html_body = render_to_string('game_app/email_template.html', data)
            msg = EmailMultiAlternatives(f'Вопрос #{message.pk}', html_body, from_email=settings.EMAIL_HOST_USER,
                                         to=[settings.EMAIL_HOST_USER, ])
            msg.content_subtype = "html"
            msg.send()
            data = {
                'topic': 'Успешно',
                'text':
                    '''Ваш вопрос успешно доставлен<br>Ожидайте ответа''',
                'user': request.user.email,
            }
            html_body = render_to_string('game_app/email_template.html', data)
            msg = EmailMultiAlternatives(f'Вопрос #{message.pk}', html_body, from_email=settings.EMAIL_HOST_USER,
                                         to=[data["user"], ])
            msg.content_subtype = "html"
            msg.send()
            return redirect('profile', request.user.username)
        else:
            return HttpResponse('error')


class SubscribeView(View):
    def post(self, request):
        topics = list(MessageTopics.objects.filter(name__in=request.POST.getlist('topics', '')))
        for topic in MessageTopics.objects.all():
            if topic in topics:
                topic.users.add(request.user)
                topic.save()
            else:
                topic.users.remove(request.user)
                topic.save()

        return redirect('support')


class ChatView(View):
    def get(self, request):
        context = {
            "room_name": "group",
            'messages': ChatMessage.objects.all(),
        }
        return render(request, template_name="game_app/chat.html", context=context)


class ChartView(View):
    def get(self, request):
        user = request.GET.get('user', request.user.username)
        user = User.objects.get(username=user)
        library = Library.objects.filter(user=user)
        pie = {}
        for game in library:
            for platform in game.game.platforms.all():
                if platform.name in pie:
                    pie[platform.name] += 1
                else:
                    pie[platform.name] = 1

        year = (datetime.now() - relativedelta(years=1)).year
        start = date(year, 1, 1)
        line = {}
        for m in range(1, 13):
            line[start.strftime('%B')] = len(
                list(Game.objects.filter(release_date__lt=start + relativedelta(months=1), release_date__gte=start)))
            start += relativedelta(months=1)
        context = {'histo': [[i, len(list(Library.objects.filter(user=user, rate=i)))] for i in range(1, 11)],
                   'pie': pie, 'line': line, 'year': year, 'user': user.username}
        return render(request, 'game_app/charts.html', context)


class RyadView(View):
    def get(self, request):
        user = request.GET.get('user', request.user.username)
        user = User.objects.get(username=user)
        year = request.GET.get('year', (datetime.now() - relativedelta(years=1)).year)
        start = date(int(year), 1, 1)
        line = {}
        table = {1: ['-', '-', '-', '-', '-', '-', '-']}
        for m in range(1, 12 * 1 + 1):
            line[m] = [len(
                list(Game.objects.filter(release_date__lt=start + relativedelta(months=1), release_date__gte=start))),
                start.year]
            start += relativedelta(months=1)
            # if m > 1:
            #     table[m] = [line[m][0], round(line[m][0] - line[m - 1][0], 2), round(line[m][0] - line[1][0], 2),
            #                 round(line[m][0] / line[m - 1][0] * 100, 2),
            #                 round(line[m][0] / line[1][0] * 100, 2), round(line[m][0] / line[m - 1][0] * 100 - 100, 2),
            #                 round(line[m][0] / line[1][0] * 100 - 100, 2)]
            # else:
            #     table[m][0] = line[m][0]
        lens = []
        start = date(2022, 1, 1)
        for m in range(0, 12):
            lens.append(len(
                list(Game.objects.filter(release_date__lt=start + relativedelta(months=1), release_date__gte=start))))
            start += relativedelta(months=1)
            if m > 0:
                table[m + 1] = [lens[m], round(lens[m] - lens[m - 1], 2), round(lens[m] - lens[0], 2),
                                round(lens[m] / lens[m - 1] * 100, 2),
                                round(lens[m] / lens[0] * 100, 2), round(lens[m] / lens[m - 1] * 100 - 100, 2),
                                round(lens[m] / lens[0] * 100 - 100, 2)]
            else:
                table[m + 1][0] = lens[m]
        users = {}
        start = datetime.now() - relativedelta(years=1)
        for m in range(1, 13):
            users[start.strftime('%B')] = len(
                list(User.objects.filter(date_joined__gte=start, date_joined__lt=start + relativedelta(months=1))))
            start += relativedelta(months=1)

        games = {}
        start = datetime.now() - relativedelta(years=1)
        for m in range(1, 13):
            games[start.strftime('%B')] = len(
                list(Library.objects.filter(added_at__gte=start, added_at__lt=start + relativedelta(months=1))))
            start += relativedelta(months=1)

        context = {'line': line,
                   'year': year,
                   'user': user.username,
                   'table': table,
                   'users': users,
                   'games': games,
                   }
        return render(request, 'game_app/lab6.html', context)


def CreateUser(request):
    num = random.randint(0, 100)
    for _ in range(0, 16):
        try:
            library = Library.objects.create(user=User.objects.get(pk=random.randint(0, 100)),
                                             game=Game.objects.get(pk=random.randint(0, 40456)))
            month = random.randint(6, 16)
            d = date(2022, month, 1) if month < 13 else date(2023, month - 12, 1)
            library.added_at = d
        except:
            pass
        else:
            library.save()
    return HttpResponse(f'added ')


class SmoothRyadView(View):
    def get(self, request):
        def FindEdgeFor5(pos, arr):
            # arr = list(map(lambda x: float(x), arr))
            # print(pos, arr)
            return (arr[0] * (-3) + arr[1] * 12 + arr[2] * 17 + arr[3] * 12 + arr[0] * (-3)) / 35 + \
                   (arr[0] * (-2) + arr[1] * (-1) + arr[3] * 1 + arr[4] * 2) * pos / 10 + \
                   (arr[0] * 2 + arr[1] * (-1) + arr[2] * (-2) + arr[3] * (-1) + arr[0] * 2) * pos * pos / 14

        user = request.GET.get('user', request.user.username)
        user = User.objects.get(username=user)
        year = request.GET.get('year', (datetime.now() - relativedelta(years=1)).year)
        start = date(int(year), 1, 1)
        line = {}
        table1 = {}
        for m in range(1, 13):
            line[m] = len(
                list(Game.objects.filter(release_date__lt=start + relativedelta(months=1), release_date__gte=start)))
            start += relativedelta(months=1)

        start = date(2022, 1, 1)
        for m in range(1, 13):
            table1[m] = []
            table1[m].append(line[m])
            if 1 < m < 12:
                table1[m].append(math.ceil((line[m - 1] + line[m] + line[m + 1]) / 3))
            else:
                match m:
                    case 1:
                        table1[m].append(math.ceil((line[1] * 5 + line[2] * 2 + line[3] * (-1)) / 6))
                    case 12:
                        table1[m].append(math.ceil((line[10] * 5 + line[11] * 2 + line[12] * (-1)) / 6))

            if 3 < m < 10:
                table1[m].append(math.ceil(
                    (line[m - 3] + line[m - 2] + line[m - 1] + line[m] + line[m + 1] + line[m + 2] + line[m + 3]) / 7))
            else:
                match m:
                    case 1:
                        table1[m].append(math.ceil((line[1] * 39 + line[2] * 8 + line[3] * 4 + line[4] * 4 + line[
                            5] * 1 + line[6] * 4 + (-2) * line[7]) / 42))
                    case 2:
                        table1[m].append(math.ceil((line[1] * 8 + line[2] * 19 + line[3] * 16 + line[4] * 6 + line[
                            5] * (-4) + line[6] * (-7) + 4 * line[7]) / 42))
                    case 3:
                        table1[m].append(math.ceil((line[1] * (-4) + line[2] * 16 + line[3] * 19 + line[4] * 12 + line[
                            5] * 2 + line[6] * (-4) + line[7]) / 42))
                    case 10:
                        table1[m].append(math.ceil((line[6] * 1 + line[7] * (-4) + line[8] * 2 + line[9] * 12 + line[
                            10] * 19 + line[11] * 16 + (-4) * line[12]) / 42))
                    case 11:
                        table1[m].append(math.ceil((line[6] * 4 + line[7] * (-7) + line[8] * (-4) + line[9] * 6 + line[
                            10] * 16 + line[11] * 19 + 8 * line[12]) / 42))
                    case 12:
                        table1[m].append(math.ceil((line[6] * 2 + line[7] * 4 + line[8] * 1 + line[9] * (-4) + line[
                            10] * 1 + line[11] * 4 + 39 * line[12]) / 42))

            if 2 < m < 11:
                table1[m].append(math.ceil((line[m - 2] * (-3) + line[m - 1] * 12 + line[m] * 17 + line[m + 1] * 12 + (
                    -3) * line[m + 2]) / 35))
            else:
                match m:
                    case 1:
                        table1[m].append(math.ceil(
                            (line[1] * 31 + line[2] * 9 + line[3] * (-3) + line[4] * (-5) + 3 * line[5]) / 35))
                    case 2:
                        table1[m].append(
                            math.ceil((line[1] * 9 + line[2] * 13 + line[3] * 12 + line[4] * 6 + (-5) * line[5]) / 35))
                    case 11:
                        table1[m].append(math.ceil(
                            (line[8] * (-5) + line[9] * 6 + line[10] * 12 + line[11] * 13 + (-9) * line[12]) / 35))
                    case 12:
                        table1[m].append(math.ceil(
                            (line[8] * 3 + line[9] * (-5) + line[10] * (-3) + line[11] * 9 + 31 * line[12]) / 35))

        table1[13] = ['-',
                      math.ceil(table1[10][0] + ((line[12] - line[11]) / 3)),
                      math.ceil(table1[10][1] + ((line[12] - line[11]) / 7)),
                      math.ceil(table1[10][2] + ((line[12] - line[11]) / 5))]

        users = {}
        start = datetime.now() - relativedelta(years=1)
        table2 = {}
        for m in range(1, 13):
            users[m] = len(
                list(User.objects.filter(date_joined__gte=start, date_joined__lt=start + relativedelta(months=1))))
            start += relativedelta(months=1)

        for m in range(1, 13):
            table2[m] = []
            table2[m].append(users[m])
            if 1 < m < 12:
                table2[m].append(math.ceil((users[m - 1] + users[m] + users[m + 1]) / 3))
            else:
                match m:
                    case 1:
                        table2[m].append(math.ceil((users[1] * 5 + users[2] * 2 + users[3] * (-1)) / 6))
                    case 12:
                        table2[m].append(math.ceil((users[10] * 5 + users[11] * 2 + users[12] * (-1)) / 6))

            if 3 < m < 10:
                table2[m].append(math.ceil((users[m - 3] + users[m - 2] + users[m - 1] + users[m] + users[m + 1] +
                                            users[m + 2] + users[m + 3]) / 7))
            else:
                match m:
                    case 1:
                        table2[m].append(math.ceil((users[1] * 39 + users[2] * 8 + users[3] * 4 + users[4] * 4 + users[
                            5] * 1 + users[6] * 4 + (-2) * users[7]) / 42))
                    case 2:
                        table2[m].append(math.ceil((users[1] * 8 + users[2] * 19 + users[3] * 16 + users[4] * 6 + users[
                            5] * (-4) + users[6] * (-7) + 4 * users[7]) / 42))
                    case 3:
                        table2[m].append(
                            math.ceil((users[1] * (-4) + users[2] * 16 + users[3] * 19 + users[4] * 12 + users[
                                5] * 2 + users[6] * (-4) + users[7]) / 42))
                    case 10:
                        table2[m].append(
                            math.ceil((users[6] * 1 + users[7] * (-4) + users[8] * 2 + users[9] * 12 + users[
                                10] * 19 + users[11] * 16 + (-4) * users[12]) / 42))
                    case 11:
                        table2[m].append(
                            math.ceil((users[6] * 4 + users[7] * (-7) + users[8] * (-4) + users[9] * 6 + users[
                                10] * 16 + users[11] * 19 + 8 * users[12]) / 42))
                    case 12:
                        table2[m].append(
                            math.ceil((users[6] * 2 + users[7] * 4 + users[8] * 1 + users[9] * (-4) + users[
                                10] * 1 + users[11] * 4 + 39 * users[12]) / 42))

            if 2 < m < 11:
                table2[m].append(math.ceil((users[m - 2] * (-3) + users[m - 1] * 12 + users[m] * 17 + users[
                    m + 1] * 12 + (-3) * users[m + 2]) / 35))
            else:
                match m:
                    case 1:
                        table2[m].append(math.ceil(
                            (users[1] * 31 + users[2] * 9 + users[3] * (-3) + users[4] * (-5) + 3 * users[5]) / 35))
                    case 2:
                        table2[m].append(
                            math.ceil(
                                (users[1] * 9 + users[2] * 13 + users[3] * 12 + users[4] * 6 + (-5) * users[5]) / 35))
                    case 11:
                        table2[m].append(math.ceil(
                            (users[8] * (-5) + users[9] * 6 + users[10] * 12 + users[11] * 13 + (-9) * users[12]) / 35))
                    case 12:
                        table2[m].append(math.ceil(
                            (users[8] * 3 + users[9] * (-5) + users[10] * (-3) + users[11] * 9 + 31 * users[12]) / 35))

        table2[13] = ['-',
                      math.ceil(table2[10][0] + ((users[12] - users[11]) / 3)),
                      math.ceil(table2[10][1] + ((users[12] - users[11]) / 7)),
                      math.ceil(table2[10][2] + ((users[12] - users[11]) / 5))]

        games = {}
        start = datetime.now() - relativedelta(years=1)
        table3 = {}
        for m in range(1, 13):
            games[m] = len(
                list(Library.objects.filter(added_at__gte=start, added_at__lt=start + relativedelta(months=1))))
            start += relativedelta(months=1)

        for m in range(1, 13):
            table3[m] = []
            table3[m].append(games[m])
            if 1 < m < 12:
                table3[m].append(math.ceil((games[m - 1] + games[m] + games[m + 1]) / 3))
            else:
                match m:
                    case 1:
                        table3[m].append(math.ceil((games[1] * 5 + games[2] * 2 + games[3] * (-1)) / 6))
                    case 12:
                        table3[m].append(math.ceil((games[10] * 5 + games[11] * 2 + games[12] * (-1)) / 6))

            if 3 < m < 10:
                table3[m].append(math.ceil((games[m - 3] + games[m - 2] + games[m - 1] + games[m] + games[m + 1] +
                                            games[m + 2] + games[m + 3]) / 7))
            else:
                match m:
                    case 1:
                        table3[m].append(math.ceil((games[1] * 39 + games[2] * 8 + games[3] * 4 + games[4] * 4 + games[
                            5] * 1 + games[6] * 4 + (-2) * games[7]) / 42))
                    case 2:
                        table3[m].append(math.ceil((games[1] * 8 + games[2] * 19 + games[3] * 16 + games[4] * 6 + games[
                            5] * (-4) + games[6] * (-7) + 4 * games[7]) / 42))
                    case 3:
                        table3[m].append(
                            math.ceil((games[1] * (-4) + games[2] * 16 + games[3] * 19 + games[4] * 12 + games[
                                5] * 2 + games[6] * (-4) + games[7]) / 42))
                    case 10:
                        table3[m].append(
                            math.ceil((games[6] * 1 + games[7] * (-4) + games[8] * 2 + games[9] * 12 + games[
                                10] * 19 + games[11] * 16 + (-4) * games[10]) / 42))
                    case 11:
                        table3[m].append(
                            math.ceil((games[6] * 4 + games[7] * (-7) + games[8] * (-4) + games[9] * 6 + games[
                                10] * 16 + games[11] * 19 + 8 * games[12]) / 42))
                    case 12:
                        table3[m].append(
                            math.ceil((games[6] * 2 + games[7] * 4 + games[8] * 1 + games[9] * (-4) + games[
                                10] * 1 + games[11] * 4 + 39 * games[12]) / 42))

            if 2 < m < 11:
                table3[m].append(math.ceil((games[m - 2] * (-3) + games[m - 1] * 12 + games[m] * 17 + games[
                    m + 1] * 12 + (-3) * games[m + 2]) / 35))
            else:
                match m:
                    case 1:
                        table3[m].append(math.ceil(
                            (games[1] * 31 + games[2] * 9 + games[3] * (-3) + games[4] * (-5) + 3 * games[5]) / 35))
                    case 2:
                        table3[m].append(
                            math.ceil(
                                (games[1] * 9 + games[2] * 13 + games[3] * 12 + games[4] * 6 + (-5) * games[5]) / 35))
                    case 11:
                        table3[m].append(math.ceil(
                            (games[8] * (-5) + games[9] * 6 + games[10] * 12 + games[11] * 13 + (-9) * games[12]) / 35))
                    case 12:
                        table3[m].append(math.ceil(
                            (games[8] * 3 + games[9] * (-5) + games[10] * (-3) + games[11] * 9 + 31 * games[12]) / 35))

        table3[13] = ['-',
                      math.ceil(table3[10][0] + ((games[12] - games[11]) / 3)),
                      math.ceil(table3[10][1] + ((games[12] - games[11]) / 7)),
                      math.ceil(table3[10][2] + ((games[12] - games[11]) / 5))]

        context = {'year': year,
                   'user': user.username,
                   'table1': table1,
                   'table2': table2,
                   'table3': table3,
                   }
        return render(request, 'game_app/lab7.html', context)


class LAB8View(View):
    def get(self, request):
        def bigtable(arr):
            total_y = 0
            total_t = 0
            total_yt = 0
            total_t_2 = 0
            total_yt_2 = 0
            total_t_4 = 0
            total_lny = 0
            total_lnyt = 0

            bigtable = {}
            for m in range(1, 13):
                y = arr[m]
                t = m - 6
                yt = y * t
                t_2 = t * t
                yt_2 = y * t_2
                t_4 = t_2 * t_2
                lny = round(math.log(y), 2) if y > 0 else 0
                lnyt = round(lny * t, 2)

                total_y += y
                total_yt += yt
                total_t_2 += t_2
                total_yt_2 += yt_2
                total_t_4 += t_4
                total_lny += lny
                total_lnyt += lnyt

                bigtable[m] = [y, t, yt, t_2, yt_2, t_4, lny, lnyt]

            bigtable['Всего'] = [total_y, total_t, total_yt, total_t_2, total_yt_2, total_t_4, total_lny, total_lnyt]
            return bigtable

        def values(arr):
            ind = 1
            max = 1
            n = 0
            for m in range(2, 12):
                if arr[m] != arr[m - 1] or m == 11:
                    n += 1
                    if arr[m] != arr[m - 1] and m == 11:
                        n += 1
                    if m - ind > max:
                        max = m - ind
                    ind = m
            return [n, max]

        def coefs(type, arr):
            l0 = arr['Всего'][0] / 12
            l1 = arr['Всего'][2] / arr['Всего'][3]

            p2 = ((12 * arr['Всего'][4]) - (arr['Всего'][3] * arr['Всего'][0])) / (
                    (12 * arr['Всего'][5]) - (arr['Всего'][3] * arr['Всего'][3]))
            p0 = l0 - (arr['Всего'][3] / 12) * p2

            pok0 = math.exp(arr['Всего'][6] / 12)
            pok1 = math.exp(arr['Всего'][7] / arr['Всего'][3])

            match type:
                case 'line':
                    return [round(l0, 2), round(l1, 2)]
                case 'parabola':
                    return [round(p0, 2), round(l1, 2), round(p2, 2)]
                case 'pokaz':
                    return [round(pok0, 2), round(pok1, 2)]

        def modelArr(type, arr):
            c = coefs(type, arr)
            match type:
                case 'line':
                    return [round(c[0] + c[1] * t, 2) for t in range(-5, 7)]
                case 'parabola':
                    return [round(c[0] + c[1] * t + c[2] * t * t, 2) for t in range(-5, 7)]
                case 'pokaz':
                    return [round(c[0] + c[1] ** t, 2) for t in range(-5, 7)]

        def equations(arr):
            line = coefs('line', arr)
            line = f'{line[0]} + {line[1]}*t'
            parabola = coefs('parabola', arr)
            parabola = f'{parabola[0]} + {parabola[1]}*t + {parabola[2]}*t^2'
            pokaz = coefs('pokaz', arr)
            pokaz = f'{pokaz[0]} + {pokaz[1]}^t'
            return [line, parabola, pokaz]

        def getModelDict(arr, num):
            line_arr = modelArr('line', arr)
            parabola_arr = modelArr('parabola', arr)
            pokaz_arr = modelArr('pokaz', arr)

            d = {}
            for m in range(1, 13):
                d[m] = []
                if num == 1:
                    d[m].append(line[m])
                elif num == 2:
                    d[m].append(users[m])
                elif num == 3:
                    d[m].append(games[m])
                d[m].append(line_arr[m - 1])
                d[m].append(parabola_arr[m - 1])
                d[m].append(pokaz_arr[m - 1])

            return d

        def findMe(arr):
            arr = [arr[m] for m in range(1, 13)]
            arr = sorted(arr)
            return (arr[7] + arr[6]) / 2

        tau = 5
        tautau = math.floor(3.3 * (math.log(12) + 1))
        result1 = math.floor(1 / 2 * (12 + 1 - 1.96 * math.sqrt(12 - 1)))
        result2 = math.floor(1 / 3 * (2 * 12 - 1) - 1.96 * math.sqrt((16 * 12 - 29) / 90))

        # user = request.GET.get('user', request.user.username)
        # user = User.objects.get(username=user)
        year = request.GET.get('year', (datetime.now() - relativedelta(years=1)).year)
        start = date(int(year), 1, 1)

        line = {}
        for m in range(1, 13):
            line[m] = len(
                list(Game.objects.filter(release_date__lt=start + relativedelta(months=1), release_date__gte=start)))
            start += relativedelta(months=1)
        table1 = {}
        table11 = {}
        for m in range(1, 12):
            table1[m] = '+' if line[m + 1] >= line[m] else '-'
        for m in range(1, 12):
            table11[m] = '+' if line[m + 1] >= findMe(line) else '-'
        me1 = findMe(line)
        n1 = values(table1)[0]
        max1 = values(table1)[1]
        n11 = values(table11)[0]
        max11 = values(table11)[1]
        result11 = (result1 < n11) and (max11 < tautau)
        result12 = (result2 < n1) and (max1 < tau)
        bigtable1 = bigtable(line)
        eq = equations(bigtable1)
        line1 = eq[0]
        parabola1 = eq[1]
        pokaz1 = eq[2]
        model1 = getModelDict(bigtable1, 1)

        users = {}
        start = datetime.now() - relativedelta(years=1)
        for m in range(1, 13):
            users[m] = len(
                list(User.objects.filter(date_joined__gte=start, date_joined__lt=start + relativedelta(months=1))))
            start += relativedelta(months=1)
        table2 = {}
        table21 = {}
        for m in range(1, 12):
            table2[m] = '+' if users[m + 1] >= users[m] else '-'
        for m in range(1, 12):
            table21[m] = '+' if users[m + 1] >= findMe(users) else '-'
        me2 = findMe(users)
        n2 = values(table2)[0]
        max2 = values(table2)[1]
        n21 = values(table21)[0]
        max21 = values(table21)[1]
        result21 = (result1 < n21) and (max21 < tautau)
        result22 = (result2 < n2) and (max2 < tau)
        bigtable2 = bigtable(users)
        eq = equations(bigtable2)
        line2 = eq[0]
        parabola2 = eq[1]
        pokaz2 = eq[2]
        model2 = getModelDict(bigtable2, 2)

        games = {}
        start = datetime.now() - relativedelta(years=1)
        for m in range(1, 13):
            games[m] = len(
                list(Library.objects.filter(added_at__gte=start, added_at__lt=start + relativedelta(months=1))))
            start += relativedelta(months=1)
        table3 = {}
        table31 = {}
        for m in range(1, 12):
            table3[m] = '+' if games[m + 1] >= games[m] else '-'
        for m in range(1, 12):
            table31[m] = '+' if games[m + 1] >= findMe(games) else '-'
        me3 = findMe(games)
        n3 = values(table3)[0]
        max3 = values(table3)[1]
        n31 = values(table31)[0]
        max31 = values(table31)[1]
        result31 = (result1 < n31) and (max31 < tautau)
        result32 = (result2 < n3) and (max3 < tau)
        bigtable3 = bigtable(games)
        eq = equations(bigtable3)
        line3 = eq[0]
        parabola3 = eq[1]
        pokaz3 = eq[2]
        model3 = getModelDict(bigtable3, 3)

        context = {'line': line,
                   'year': year,
                   # 'user': user.username,
                   'users': users,
                   'games': games,
                   'table1': table1,
                   'table11': table11,
                   'max1': max1,
                   'n1': n1,
                   'max11': max11,
                   'n11': n11,
                   'table2': table2,
                   'max2': max2,
                   'n2': n2,
                   'table21': table21,
                   'max21': max21,
                   'n21': n21,
                   'table3': table3,
                   'max3': max3,
                   'n3': n3,
                   'table31': table31,
                   'max31': max31,
                   'n31': n31,
                   'tau': tau,
                   'tautau': tautau,
                   'result1': result1,
                   'result2': result2,
                   'result11': result11,
                   'result12': result12,
                   'result21': result21,
                   'result22': result22,
                   'result31': result31,
                   'result32': result32,

                   'bigtable1': bigtable1,
                   'bigtable2': bigtable2,
                   'bigtable3': bigtable3,

                   'line1': line1,
                   'parabola1': parabola1,
                   'pokaz1': pokaz1,

                   'line2': line2,
                   'parabola2': parabola2,
                   'pokaz2': pokaz2,

                   'line3': line3,
                   'parabola3': parabola3,
                   'pokaz3': pokaz3,

                   'model1': model1,
                   'model2': model2,
                   'model3': model3,

                   'me1': me1,
                   'me2': me2,
                   'me3': me3,
                   }
        return render(request, 'game_app/lab8.html', context)


class LAB9View(View):
    def get(self, request):
        def viborka():
            line = {}
            graph = int(request.GET.get('num', 0))
            match graph:
                case 1:
                    year = request.GET.get('year', (datetime.now() - relativedelta(years=1)).year)
                    # start = date(int(year), 1, 1)
                    start = date(2000, 1, 1)
                    for m in range(1, 13):
                        line[m] = len(list(Game.objects.filter(release_date__lt=start + relativedelta(months=1),
                                                               release_date__gte=start)))
                        start += relativedelta(months=1)
                    title = "График динамики выхода игр за 2022 год"
                case 2:
                    start = datetime.now() - relativedelta(years=1)
                    for m in range(1, 13):
                        line[m] = len(list(User.objects.filter(date_joined__gte=start,
                                                               date_joined__lt=start + relativedelta(months=1))))
                        start += relativedelta(months=1)
                    title = "График динамики регистраций новых пользователей за последние 12 месяцев"
                case 3:
                    start = datetime.now() - relativedelta(years=1)
                    for m in range(1, 13):
                        line[m] = len(list(
                            Library.objects.filter(added_at__gte=start, added_at__lt=start + relativedelta(months=1))))
                        start += relativedelta(months=1)
                    title = "График динамики активности добавления игр в личные библиотеки за последние 12 месяцев"
            return [line, title]

        def bigtable(arr):
            total_y = 0
            total_t = 0
            total_yt = 0
            total_t_2 = 0
            total_yt_2 = 0
            total_t_4 = 0
            total_lny = 0
            total_lnyt = 0

            bigtable = {}
            for m in range(1, 13):
                y = arr[m]
                t = m - 6
                yt = y * t
                t_2 = t * t
                yt_2 = y * t_2
                t_4 = t_2 * t_2
                lny = round(math.log(y), 2) if y > 0 else 0
                lnyt = round(lny * t, 2)

                total_y += y
                total_yt += yt
                total_t_2 += t_2
                total_yt_2 += yt_2
                total_t_4 += t_4
                total_lny += lny
                total_lnyt += lnyt

                bigtable[m] = [y, t, yt, t_2, yt_2, t_4, lny, lnyt]

            bigtable['Всего'] = [total_y, total_t, total_yt, total_t_2, total_yt_2, total_t_4, total_lny, total_lnyt]
            return bigtable

        def values(arr):
            ind = 1
            max = 1
            n = 0
            for m in range(2, 12):
                if arr[m] != arr[m - 1] or m == 11:
                    n += 1
                    if arr[m] != arr[m - 1] and m == 11:
                        n += 1
                    if m - ind > max:
                        max = m - ind
                    ind = m
            return [n, max]

        def coefs(type, arr):
            l0 = arr['Всего'][0] / 12
            l1 = arr['Всего'][2] / arr['Всего'][3]

            p2 = ((12 * arr['Всего'][4]) - (arr['Всего'][3] * arr['Всего'][0])) / (
                    (12 * arr['Всего'][5]) - (arr['Всего'][3] * arr['Всего'][3]))
            p0 = l0 - (arr['Всего'][3] / 12) * p2

            pok0 = math.exp(arr['Всего'][6] / 12)
            pok1 = math.exp(arr['Всего'][7] / arr['Всего'][3])

            match type:
                case 'line':
                    return [round(l0, 2), round(l1, 2)]
                case 'parabola':
                    return [round(p0, 2), round(l1, 2), round(p2, 2)]
                case 'pokaz':
                    return [round(pok0, 2), round(pok1, 2)]

        def modelArr(type, arr):
            c = coefs(type, arr)
            match type:
                case 'line':
                    return [round(c[0] + c[1] * t, 2) for t in range(-5, 7)]
                case 'parabola':
                    return [round(c[0] + c[1] * t + c[2] * t * t, 2) for t in range(-5, 7)]
                case 'pokaz':
                    return [round(c[0] + c[1] ** t, 2) for t in range(-5, 7)]

        def equations(arr):
            line = coefs('line', arr)
            line = f'{line[0]} + {line[1]}*t'
            parabola = coefs('parabola', arr)
            parabola = f'{parabola[0]} + {parabola[1]}*t + {parabola[2]}*t^2'
            pokaz = coefs('pokaz', arr)
            pokaz = f'{pokaz[0]} + {pokaz[1]}^t'
            return [line, parabola, pokaz]

        def getModelDict(arr):
            line_arr = modelArr('line', arr)
            parabola_arr = modelArr('parabola', arr)
            pokaz_arr = modelArr('pokaz', arr)

            d = {}
            for m in range(1, 13):
                d[m] = []
                d[m].append(line[m])
                d[m].append(line_arr[m - 1])
                d[m].append(parabola_arr[m - 1])
                d[m].append(pokaz_arr[m - 1])

            return d

        def findMe(arr):
            arr = [arr[m] for m in range(1, 13)]
            arr = sorted(arr)
            return (arr[7] + arr[6]) / 2

        def getLine(t):
            c = coefs('line', bigtable)
            return round(c[0] + c[1] * t, 2)

        def getParabola(t):
            c = coefs('parabola', bigtable)
            return round(c[0] + c[1] * t + c[2] * t * t, 2)

        def getPokaz(t):
            c = coefs('pokaz', bigtable)
            return round(c[0] + c[1] ** t, 2)

        def ostatok(arr, func):
            ostatok = {}
            for m in range(1, 13):
                ostatok[m] = round(arr[m] - func(m - 6), 2)
            return ostatok

        def task1(arr):  # arr - ostatok ryad
            table_me = {}
            me = findMe(arr)
            for m in range(1, 12):
                table_me[m] = '+' if arr[m + 1] >= me else '-'
            n = values(table_me)[0]
            max = values(table_me)[1]
            result = (result1 < n) and (max < tautau)
            # result2 = (result2 < n1) and (max1 < tau)
            return {'table': table_me, 'n': n, 'max': max, 'result': result, 'me': me}

        def task2(arr):
            sum_2 = 0
            sum_3 = 0
            sum_4 = 0
            n = 12

            for m in range(1, 13):
                sum_2 = arr[m] ** 2
                sum_3 = arr[m] ** 3
                sum_4 = arr[m] ** 4

            A = round((sum_3 / n) / math.sqrt((sum_2 / n) ** 3), 2)
            E = round((sum_4 / n) / math.sqrt((sum_2 / n) ** 3) - 3, 2)

            test1 = math.sqrt(6 * 10 / 13 / 15)
            test2 = math.sqrt(24 * 12 * 10 * 9 / 13 / 13 / 15 / 17)

            check1 = round(1.5 * test1, 2)
            check2 = round(1.5 * test2, 2)

            check3 = round(2 * test1, 2)
            check4 = round(2 * test2, 2)

            result1 = abs(A) < check1 and abs(E + 6 / 13) < check2
            result2 = abs(A) >= check3 or abs(E + 6 / 13) >= check4

            return {'A': A, 'E': E, 'check1': check1 if result1 else check3, 'check2': check2 if result1 else check4,
                    "result": result1}

        def task3(arr, func):
            table = {}
            e_2_total = 0
            e_diff_total = 0
            for m in range(1, 13):
                table[m] = [line[m], m - 6, func(m - 6), arr[m], round(arr[m] ** 2, 2)]
                e_2_total += arr[m] ** 2
            table[1].append('-')
            for m in range(2, 13):
                table[m].append(round((table[m][-2] - table[m - 1][-3]) ** 2, 2))
                e_diff_total += table[m][-1]

            d1 = 0.97
            du = 1.33

            d = round(e_diff_total / e_2_total, 2)
            result = d1 <= d <= du
            check = None if result else False if d < d1 else True
            return {'table': table, "e_2": round(e_2_total, 2), "e_diff": round(e_diff_total, 2), 'result': result,
                    'check': check, "d1": d1, 'du': du, 'd': d}

        def task4(model):
            arr = modelArr(model, bigtable)
            sum = 0
            for m in range(1, 13):
                sum += abs((arr[m - 1] - line[m]) / line[m]) if line[m] > 0 else abs((arr[m - 1] - line[m]) / 1)

            MAPE = round(100 * (sum / 12), 2)
            S = round(math.sqrt(sum / 12), 2)
            SSE = round(sum, 2)
            MSE = round(SSE / 10, 2)

            if MAPE < 10:
                result = 'Так как MAPE < 10%, модель имеет высокую точность'
            elif 10 <= MAPE <= 20:
                result = 'Так как 10% <= MAPE <= 20%, модель можно считать хорошей'
            elif 20 < MAPE < 50:
                result = 'Так как 20% < MAPE < 50%, модель можно считать удовлетворительной'
            else:
                result = 'Так как MAPE > 50%, модель можно считать плохой'

            return {"mape": MAPE, 's': S, 'sse': SSE, 'mse': MSE, 'result': result}

        tau = 5
        tautau = math.floor(3.3 * (math.log(12) + 1))
        result1 = math.floor(1 / 2 * (12 + 1 - 1.96 * math.sqrt(12 - 1)))
        result2 = math.floor(1 / 3 * (2 * 12 - 1) - 1.96 * math.sqrt((16 * 12 - 29) / 90))

        line, title = viborka()
        bigtable = bigtable(line)

        ostatok_line = ostatok(line, getLine)
        task1_line = task1(ostatok_line)
        task2_line = task2(ostatok_line)
        task3_line = task3(ostatok_line, getLine)
        task4_line = task4('line')

        ostatok_parabola = ostatok(line, getParabola)
        task1_parabola = task1(ostatok_parabola)
        task2_parabola = task2(ostatok_parabola)
        task3_parabola = task3(ostatok_parabola, getParabola)
        task4_parabola = task4('parabola')

        ostatok_pokaz = ostatok(line, getPokaz)
        task1_pokaz = task1(ostatok_pokaz)
        task2_pokaz = task2(ostatok_pokaz)
        task3_pokaz = task3(ostatok_pokaz, getPokaz)
        task4_pokaz = task4('pokaz')

        eq = equations(bigtable)
        line_form = eq[0]
        parabola_form = eq[1]
        pokaz_form = eq[2]
        model = getModelDict(bigtable)

        context = {'line': line,
                   'bigtable': bigtable,
                   'line_form': line_form,
                   "parabola_form": parabola_form,
                   "pokaz_form": pokaz_form,
                   "model": model,
                   "ostatok": ostatok,
                   "ostatok_line": ostatok_line,
                   "ostatok_parabola": ostatok_parabola,
                   "ostatok_pokaz": ostatok_pokaz,
                   "task1_line": task1_line,
                   "task2_line": task2_line,
                   "task3_line": task3_line,
                   "task4_line": task4_line,
                   "task1_parabola": task1_parabola,
                   "task2_parabola": task2_parabola,
                   "task3_parabola": task3_parabola,
                   "task4_parabola": task4_parabola,
                   "task1_pokaz": task1_pokaz,
                   "task2_pokaz": task2_pokaz,
                   "task3_pokaz": task3_pokaz,
                   "task4_pokaz": task4_pokaz,
                   "test1": result1,
                   "test2": result2,
                   'tau': tau,
                   'tautau': tautau,
                   "title": title,
                   }
        return render(request, 'game_app/lab9.html', context)


class LAB10View(View):
    def get(self, request):
        def Task1():
            start = date(2015, 1, 1)
            result = {}
            mobile = Game.objects.filter(platforms__in=[7, 8])
            console = Game.objects.filter(platforms__in=[5, 4, 3, 1])
            desktop = Game.objects.filter(platforms__in=[2, 6])
            for m in range(0, 6):
                result[start.year + m] = []
                result[start.year + m].append(len(list(mobile.filter(release_date__gte=start + relativedelta(years=m),
                                                                     release_date__lt=start + relativedelta(
                                                                         years=m + 1)))))
                result[start.year + m].append(len(list(console.filter(release_date__gte=start + relativedelta(years=m),
                                                                      release_date__lt=start + relativedelta(
                                                                          years=m + 1)))))
                result[start.year + m].append(len(list(desktop.filter(release_date__gte=start + relativedelta(years=m),
                                                                      release_date__lt=start + relativedelta(
                                                                          years=m + 1)))))
            return result

        def Task2():
            # x - кол-во писем, отправленных по теме
            # y - кол-во рассылок по теме
            # size - кол-во подписчиков темы
            # region - тема рассылки
            # id - сокращение тем рассылок
            result = {}
            start = datetime(2023, 1, 1)
            topics = MessageTopics.objects.all()
            for t in topics:
                messages = Message.objects.filter(topic=t)
                y = len(list(messages))
                x = 0
                for m in messages:
                    x += len(list(m.shown_to.all()))
                size = len(list(t.users.all()))
                region = t.name
                id = ''
                if 'Добав' in region:
                    id = 'ADD'
                elif 'Обнов' in region:
                    id = 'UPD'
                else:
                    id = 'T' + region[-1]
                result[id] = [x, y, region, size]

            return result

        def Task3():
            result = []
            start = datetime(2015, 1, 1)
            while start != datetime(2016, 1, 1):
                result.append(
                    {
                        'year': start.year,
                        'month': start.month - 1,
                        'day': start.day,
                        'count': Game.objects.filter(release_date=start).count()
                    }
                )
                start += relativedelta(days=1)

            return result
        def Task4():
            result = [['Популярные жанры', '', '']]
            genres = [4, 24, 30, 33, 51]
            for genre in genres:
                name = Genres.objects.get(pk=genre).name
                result.append([name, 'Популярные жанры', ''])
                games = Game.objects.filter(genres__in=[genre])[:5]
                for game in games:
                    result.append([game.name, name, ''])
            return result

        def Task6():
            result = []
            platform = {"Мобил. устройства": [7, 8],
                        "Консол. устройства": [5, 4, 3, 1],
                        "Настол. устройства": [2, 6],
                        }
            mode = {"Для одного игрока": 46,
                    "Для онлайн игры": 47,
                    }
            for name, arr in platform.items():
                for genre, id in mode.items():
                    el = [name, genre, len(Game.objects.filter(platforms__in=arr, genres__in=[id]))]
                    # print(el)
                    result.append(el)

            return result

        context = {"task1": Task1(),
                   "task2": Task2(),
                   "task3": Task3(),
                   "task4": Task4(),
                   "task6": Task6(),
                   }
        return render(request, 'game_app/lab10.html', context)

class LAB9dopView(View):
    def get(self, request):
        n = 12*20
        def viborka():
            n = 12 * 20
            line = {}
            year = request.GET.get('year', (datetime.now() - relativedelta(years=1)).year)
            # start = date(int(year), 1, 1)
            start = date(2000, 1, 1)
            for m in range(1, n+1):
                line[m] = len(list(Game.objects.filter(release_date__lt=start + relativedelta(months=1),
                                                       release_date__gte=start)))
                start += relativedelta(months=1)
            title = "График динамики выхода игр c 2000 годf"
            return [line, title]

        def bigtable(arr):
            n = 12*20
            total_y = 0
            total_t = 0
            total_yt = 0
            total_t_2 = 0
            total_yt_2 = 0
            total_t_4 = 0
            total_lny = 0
            total_lnyt = 0

            bigtable = {}
            for m in range(1, n+1):
                y = arr[m]
                t = m - 6
                yt = y * t
                t_2 = t * t
                yt_2 = y * t_2
                t_4 = t_2 * t_2
                lny = round(math.log(y), 2) if y > 0 else 0
                lnyt = round(lny * t, 2)

                total_y += y
                total_yt += yt
                total_t_2 += t_2
                total_yt_2 += yt_2
                total_t_4 += t_4
                total_lny += lny
                total_lnyt += lnyt

                bigtable[m] = [y, t, yt, t_2, yt_2, t_4, lny, lnyt]

            bigtable['Всего'] = [total_y, total_t, total_yt, total_t_2, total_yt_2, total_t_4, total_lny, total_lnyt]
            return bigtable

        def values(arr):
            n = 12*20
            ind = 1
            max = 1
            nn = 0
            for m in range(2, n):
                if arr[m] != arr[m - 1] or m == n-1:
                    nn += 1
                    if arr[m] != arr[m - 1] and m == n-1:
                        nn += 1
                    if m - ind > max:
                        max = m - ind
                    ind = m
            return [nn, max]

        def coefs(type, arr):
            n = 12*20
            l0 = arr['Всего'][0] / n
            l1 = arr['Всего'][2] / arr['Всего'][3]

            p2 = ((n * arr['Всего'][4]) - (arr['Всего'][3] * arr['Всего'][0])) / (
                    (n * arr['Всего'][5]) - (arr['Всего'][3] * arr['Всего'][3]))
            p0 = l0 - (arr['Всего'][3] / n) * p2

            pok0 = math.exp(arr['Всего'][6] / n)
            pok1 = math.exp(arr['Всего'][7] / arr['Всего'][3])

            match type:
                case 'line':
                    return [round(l0, 2), round(l1, 2)]
                case 'parabola':
                    return [round(p0, 2), round(l1, 2), round(p2, 2)]
                case 'pokaz':
                    return [round(pok0, 2), round(pok1, 2)]

        def modelArr(type, arr):
            c = coefs(type, arr)
            match type:
                case 'line':
                    return [round(c[0] + c[1] * t, 2) for t in range(-119, 121)]
                case 'parabola':
                    return [round(c[0] + c[1] * t + c[2] * t * t, 2) for t in range(-119, 121)]
                case 'pokaz':
                    return [round(c[0] + c[1] ** t, 2) for t in range(-119, 121)]

        def equations(arr):
            line = coefs('line', arr)
            line = f'{line[0]} + {line[1]}*t'
            parabola = coefs('parabola', arr)
            parabola = f'{parabola[0]} + {parabola[1]}*t + {parabola[2]}*t^2'
            pokaz = coefs('pokaz', arr)
            pokaz = f'{pokaz[0]} + {pokaz[1]}^t'
            return [line, parabola, pokaz]

        def getModelDict(arr):
            n = 12*20
            line_arr = modelArr('line', arr)
            parabola_arr = modelArr('parabola', arr)
            pokaz_arr = modelArr('pokaz', arr)

            d = {}
            for m in range(1, n+1):
                d[m] = []
                d[m].append(line[m])
                d[m].append(line_arr[m - 1])
                d[m].append(parabola_arr[m - 1])
                d[m].append(pokaz_arr[m - 1])

            return d

        def findMe(arr):
            n = 12*20
            arr = [arr[m] for m in range(1, n+1)]
            arr = sorted(arr)
            return (arr[round(n/2)] + arr[round(n/2+1)]) / 2

        def getLine(t):
            c = coefs('line', bigtable)
            return round(c[0] + c[1] * t, 2)

        def getParabola(t):
            c = coefs('parabola', bigtable)
            return round(c[0] + c[1] * t + c[2] * t * t, 2)

        def getPokaz(t):
            c = coefs('pokaz', bigtable)
            return round(c[0] + c[1] ** t, 2)

        def ostatok(arr, func):
            n = 12*20
            ostatok = {}
            for m in range(1, n+1):
                ostatok[m] = round(arr[m] - func(m - 6), 2)
            return ostatok

        def task1(arr):  # arr - ostatok ryad
            n = 12*20
            table_me = {}
            me = findMe(arr)
            for m in range(1, n):
                table_me[m] = '+' if arr[m + 1] >= me else '-'
            x = values(table_me)[0]
            max = values(table_me)[1]
            result = (result1 < x) and (max < tautau)
            # result2 = (result2 < n1) and (max1 < tau)
            return {'table': table_me, 'n': x, 'max': max, 'result': result, 'me': me}

        def task2(arr):
            sum_2 = 0
            sum_3 = 0
            sum_4 = 0
            n = 12*20

            for m in range(1, n+1):
                sum_2 = arr[m] ** 2
                sum_3 = arr[m] ** 3
                sum_4 = arr[m] ** 4

            A = round((sum_3 / n) / math.sqrt((sum_2 / n) ** 3), 2)
            E = round((sum_4 / n) / math.sqrt((sum_2 / n) ** 3) - 3, 2)

            test1 = math.sqrt(6 * 10 / 13 / 15)
            test2 = math.sqrt(24 * 12 * 10 * 9 / 13 / 13 / 15 / 17)

            check1 = round(1.5 * test1, 2)
            check2 = round(1.5 * test2, 2)

            check3 = round(2 * test1, 2)
            check4 = round(2 * test2, 2)

            result1 = abs(A) < check1 and abs(E + 6 / 13) < check2
            result2 = abs(A) >= check3 or abs(E + 6 / 13) >= check4

            return {'A': A, 'E': E, 'check1': check1 if result1 else check3, 'check2': check2 if result1 else check4,
                    "result": result1}

        def task3(arr, func):
            n = 12*20
            table = {}
            e_2_total = 0
            e_diff_total = 0
            for m in range(1, n+1):
                table[m] = [line[m], m - 6, func(m - 6), arr[m], round(arr[m] ** 2, 2)]
                e_2_total += arr[m] ** 2
            table[1].append('-')
            for m in range(2, n+1):
                table[m].append(round((table[m][-2] - table[m - 1][-3]) ** 2, 2))
                e_diff_total += table[m][-1]

            d1 = 0.97
            du = 1.33

            d = round(e_diff_total / e_2_total, 2)
            result = d1 <= d <= du
            check = None if result else False if d < d1 else True
            return {'table': table, "e_2": round(e_2_total, 2), "e_diff": round(e_diff_total, 2), 'result': result,
                    'check': check, "d1": d1, 'du': du, 'd': d}

        def task4(model):
            n = 12*20
            arr = modelArr(model, bigtable)
            sum = 0
            for m in range(1, n+1):
                sum += abs((arr[m - 1] - line[m]) / line[m]) if line[m] > 0 else abs((arr[m - 1] - line[m]) / 1)

            MAPE = round(100 * (sum / n), 2)
            S = round(math.sqrt(sum / n), 2)
            SSE = round(sum, 2)
            MSE = round(SSE / n-2, 2)

            if MAPE < 10:
                result = 'Так как MAPE < 10%, модель имеет высокую точность'
            elif 10 <= MAPE <= 20:
                result = 'Так как 10% <= MAPE <= 20%, модель можно считать хорошей'
            elif 20 < MAPE < 50:
                result = 'Так как 20% < MAPE < 50%, модель можно считать удовлетворительной'
            else:
                result = 'Так как MAPE > 50%, модель можно считать плохой'

            return {"mape": MAPE, 's': S, 'sse': SSE, 'mse': MSE, 'result': result}

        tau = 5
        tautau = math.floor(3.3 * (math.log(n) + 1))
        result1 = math.floor(1 / 2 * (n + 1 - 1.96 * math.sqrt(n - 1)))
        result2 = math.floor(1 / 3 * (2 * n - 1) - 1.96 * math.sqrt((16 * n - 29) / 90))

        line, title = viborka()
        bigtable = bigtable(line)

        ostatok_line = ostatok(line, getLine)
        task1_line = task1(ostatok_line)
        task2_line = task2(ostatok_line)
        task3_line = task3(ostatok_line, getLine)
        task4_line = task4('line')

        ostatok_parabola = ostatok(line, getParabola)
        task1_parabola = task1(ostatok_parabola)
        task2_parabola = task2(ostatok_parabola)
        task3_parabola = task3(ostatok_parabola, getParabola)
        task4_parabola = task4('parabola')

        ostatok_pokaz = ostatok(line, getPokaz)
        task1_pokaz = task1(ostatok_pokaz)
        task2_pokaz = task2(ostatok_pokaz)
        task3_pokaz = task3(ostatok_pokaz, getPokaz)
        task4_pokaz = task4('pokaz')

        eq = equations(bigtable)
        line_form = eq[0]
        parabola_form = eq[1]
        pokaz_form = eq[2]
        model = getModelDict(bigtable)

        context = {'line': line,
                   'bigtable': bigtable,
                   'line_form': line_form,
                   "parabola_form": parabola_form,
                   "pokaz_form": pokaz_form,
                   "model": model,
                   "ostatok": ostatok,
                   "ostatok_line": ostatok_line,
                   "ostatok_parabola": ostatok_parabola,
                   "ostatok_pokaz": ostatok_pokaz,
                   "task1_line": task1_line,
                   "task2_line": task2_line,
                   "task3_line": task3_line,
                   "task4_line": task4_line,
                   "task1_parabola": task1_parabola,
                   "task2_parabola": task2_parabola,
                   "task3_parabola": task3_parabola,
                   "task4_parabola": task4_parabola,
                   "task1_pokaz": task1_pokaz,
                   "task2_pokaz": task2_pokaz,
                   "task3_pokaz": task3_pokaz,
                   "task4_pokaz": task4_pokaz,
                   "test1": result1,
                   "test2": result2,
                   'tau': tau,
                   'tautau': tautau,
                   "title": title,
                   }
        return render(request, 'game_app/lab9.html', context)