from flask import Flask, Blueprint, render_template
from flask_login import login_required, current_user, LoginManager
from flask_sqlalchemy import SQLAlchemy
from bs4 import BeautifulSoup
import html5lib
import lxml
from requests import get
import time, sys, cherrypy, os
import psutil
import pandas as pd
from paste.translogger import TransLogger

main = Blueprint('main', __name__)

from movie_engine import RecommendationEngine
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# init SQLAlchemy so we can use it later in our models
db = SQLAlchemy()

def create_app(spark_context, dataset_path):
    global recommendation_engine
    from movie_engine import RecommendationEngine
    recommendation_engine = RecommendationEngine(spark_context, dataset_path)

    app = Flask(__name__)

    app.config['SECRET_KEY'] = '9OLWxND4o83j4K4iuopO'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        # since the user_id is just the primary key of our user table, use it in the query for the user
        return User.query.get(int(user_id))

    # blueprint for auth routes in our app
    from auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    # blueprint for non-auth parts of app
    from main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app


def get_newest_movies_info():
    url = "https://www.imdb.com/movies-in-theaters/"
    response = get(url)
    # html_soup = BeautifulSoup(response.text, 'html.parser')
    html_soup = BeautifulSoup(response.text, 'lxml')

    movie_containers = html_soup.find_all('div', class_='image')
    newmovie_src = []
    title = []
    number = []
    for i in range(len(movie_containers)):
        newmovie_src.append(movie_containers[i].a.div.img['src'])
        title.append(movie_containers[i].a.div.img['title'])
        number.append(movie_containers[i].a['href'].split('/')[2])

    url = []
    for i in number:
        url.append('https://www.imdb.com/showtimes/title/%s/?ref_=inth_ov_sh' % i)

    cinemas_name = []
    for i in url:
        span_name = []
        showtime_response = get(i)
        # showtime_html_soup = BeautifulSoup(showtime_response.text, 'html.parser')
        showtime_html_soup = BeautifulSoup(showtime_response.text, 'lxml')
        new_movie_containers = showtime_html_soup.find_all('div', class_="fav_box")

        for i in range(len(new_movie_containers)):
            span_name.append(new_movie_containers[i].h3.a.span.text)

        cinemas_name.append(span_name)

    return newmovie_src, title, cinemas_name


@main.route('/')
def index():
    return render_template('index.html')

@main.route('/contact')
def contact():
    return render_template('contact.html')

@main.route('/profile')
@login_required
def profile():
    user_id = current_user.id
    print('user is', user_id)
    return render_template('profile.html', name=current_user.name)

@main.route('/home')
@login_required
def home():
    user_id = current_user.id
    print('user is', user_id)
    # get the newest movie information
    newmovie_src, newmovie_title, cinemas_name = get_newest_movies_info()

    return render_template('home.html', user_id=user_id, newmovie_src=newmovie_src,
                           newmovie_title=newmovie_title, cinemas_name=cinemas_name)

@main.route('/recommend')
@login_required
def recommend():
    user_id = current_user.id
    print('user is', user_id)
    logger.debug("User %s TOP ratings requested", user_id)
    # show top 10 movies
    top_ratings = recommendation_engine.get_top_ratings(user_id, 10)
    print("Spark Done!")
    movie_file = pd.read_csv('C:/Users/xuand/FlaskAuthSpark/datasets/ml-latest-small/movies.csv')

    def get_poster_online(movieId):
        links = pd.read_csv('C:/Users/xuand/FlaskAuthSpark/datasets/ml-latest-small/links.csv')
        number = 'tt00'
        imdbId = list(links.loc[links['movieId'] == movieId, 'imdbId'])
        number += str(imdbId[0])
        url = 'https://www.imdb.com/title/%s' % number

        response = get(url)
        # html_soup = BeautifulSoup(response.content, 'html5lib')
        html_soup = BeautifulSoup(response.content, 'lxml')
        movie_containers = html_soup.find('img')
        poster_url = movie_containers.get('src')

        return poster_url

    url_list = []
    movie_name_list = []
    genres_list = []
    for i in range(len(top_ratings)):
        movieId = recommendation_engine.movies_RDD.filter(lambda movie: movie[1] == top_ratings[i][0]).take(1)[0][0]
        poster_url = get_poster_online(movieId)
        url_list.append(poster_url)

        movie_name = list(movie_file.loc[movie_file['movieId'] == movieId, 'title'])
        movie_name_list.append(movie_name)

        genres = list(movie_file.loc[movie_file['movieId'] == movieId, 'genres'])
        genres_list.append(genres)

    tmp_genre = []
    movie_genres = []
    for genre in genres_list:
        for i in genre:
            tmp_genre.append(i)
        movie_genres.append(tmp_genre)
        tmp_genre = []

    movie_genres_list = []
    for i in movie_genres:
        tmp = i[0].split('|')
        movie_genres_list.append(tmp)
    print("Processing done!")
    return render_template('recommend.html', user_id=user_id, url_list=url_list,
                            movie_name_list=movie_name_list, movie_genres_list=movie_genres_list)


@main.route('/history')
@login_required
def history():
    user_id = current_user.id
    logger.debug("User %s history", user_id)
    # number of movies user_id rated, top 10 high/low ratings
    rated_number, user_rated_movies_high, user_rated_movies_low = recommendation_engine.get_rated_movies(user_id)

    movie_file = pd.read_csv('C:/Users/xuand/FlaskAuthSpark/datasets/ml-latest-small/movies.csv')

    def get_poster_online(movieId):
        links = pd.read_csv('C:/Users/xuand/FlaskAuthSpark/datasets/ml-latest-small/links.csv')
        number = 'tt00'
        imdbId = list(links.loc[links['movieId'] == movieId, 'imdbId'])
        number += str(imdbId[0])
        url = 'https://www.imdb.com/title/%s' % number

        response = get(url)
        # html_soup = BeautifulSoup(response.content, 'html5lib')
        html_soup = BeautifulSoup(response.content, 'lxml')
        movie_containers = html_soup.find('img')
        poster_url = movie_containers.get('src')

        return poster_url

    def get_movie_name(movieId):
        name = list(movie_file.loc[movie_file['movieId'] == movieId, 'title'])
        return name

    high_movie_year_name = []
    low_movie_year_name = []
    for i in user_rated_movies_high:
        tmp_name_high = get_movie_name(i[1])
        high_movie_year_name.append(tmp_name_high[0])
    for i in user_rated_movies_low:
        tmp_name_low = get_movie_name(i[1])
        low_movie_year_name.append(tmp_name_low[0])

    high_rated_movie_list = []
    for i in range(len(user_rated_movies_high)):
        movieId = user_rated_movies_high[i][1]
        high_rated_movie_url = get_poster_online(movieId)
        high_rated_movie_list.append(high_rated_movie_url)

    low_rated_movie_list = []
    for i in range(len(user_rated_movies_low)):
        movieId = user_rated_movies_low[i][1]
        low_rated_movie_url = get_poster_online(movieId)
        low_rated_movie_list.append(low_rated_movie_url)
    return render_template('history.html', user_id=user_id, rated_number=rated_number,
                           high_rated_movie_list=high_rated_movie_list,
                           low_rated_movie_list=low_rated_movie_list,
                           low_movie_year_name=low_movie_year_name,
                           high_movie_year_name=high_movie_year_name)