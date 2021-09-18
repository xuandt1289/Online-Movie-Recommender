from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import time, sys, cherrypy, os
import psutil
from paste.translogger import TransLogger

from main import create_app
from pyspark import SparkContext, SparkConf

def init_spark_context():
    import findspark
    findspark.init()

    import pyspark
    from pyspark.sql import SparkSession

    # load spark context
    conf = SparkConf().setAppName("movie_recommendation-server").setMaster('local')
    # IMPORTANT: pass aditional Python modules to each worker
    sc = SparkContext(conf=conf, pyFiles=['movie_engine.py'])

    return sc


# Init spark context and load libraries
sc = init_spark_context()
dataset_path = os.path.join('datasets', 'ml-latest-small')

app = create_app(sc, dataset_path)

if __name__ == "__main__":
    app.run()

