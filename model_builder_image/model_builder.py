from pyspark.sql import SparkSession
import os
from datetime import datetime
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pymongo import MongoClient
from concurrent.futures import ThreadPoolExecutor, wait
from pyspark.ml.classification import (
    LogisticRegression,
    DecisionTreeClassifier,
    RandomForestClassifier,
    GBTClassifier,
    NaiveBayes,
    LinearSVC
)

SPARKMASTER_HOST = "SPARKMASTER_HOST"
SPARKMASTER_PORT = "SPARKMASTER_PORT"
SPARK_DRIVER_PORT = "SPARK_DRIVER_PORT"
MODEL_BUILDER_HOST_NAME = "MODEL_BUILDER_HOST_NAME"


class ModelBuilderInterface():
    def build_model(self, database_url_training, database_url_test,
                    preprocessor_code, classificators_list):
        pass


class DatabaseInterface():
    def get_filenames(self):
        pass

    def find_one(self, filename, query):
        pass


class RequestValidatorInterface():
    MESSAGE_INVALID_TRAINING_FILENAME = "invalid_training_filename"
    MESSAGE_INVALID_TEST_FILENAME = "invalid_test_filename"
    MESSAGE_INVALID_CLASSIFICATOR = "invalid_classificator_name"

    def training_filename_validator(self, training_filename):
        pass

    def test_filename_validator(self, test_filename):
        pass

    def model_classificators_validator(self, classificators_list):
        pass


class SparkModelBuilder(ModelBuilderInterface):
    METADATA_DOCUMENT_ID = 0
    DOCUMENT_ID_NAME = "_id"

    def __init__(self):
        self.spark_session = SparkSession \
            .builder \
            .appName("model_builder") \
            .config("spark.driver.port",
                    os.environ[SPARK_DRIVER_PORT]) \
            .config("spark.driver.host",
                    os.environ[MODEL_BUILDER_HOST_NAME])\
            .config('spark.jars.packages',
                    'org.mongodb.spark:mongo-spark' +
                    '-connector_2.11:2.4.2')\
            .config("spark.memory.fraction", 0.8) \
            .config("spark.executor.memory", "1g") \
            .config("spark.sql.shuffle.partitions", "800") \
            .config("spark.memory.offHeap.enabled", 'true')\
            .config("spark.memory.offHeap.size", "1g")\
            .config("spark.scheduler.mode", "FAIR")\
            .master("spark://" +
                    os.environ[SPARKMASTER_HOST] +
                    ':' + str(os.environ[SPARKMASTER_PORT])) \
            .getOrCreate()

        self.thread_pool = ThreadPoolExecutor()

    def file_processor(self, database_url):
        file = self.spark_session.read.format("mongo").option(
            "uri", database_url).load()

        file_without_metadata = file.filter(
            file[self.DOCUMENT_ID_NAME] != self.METADATA_DOCUMENT_ID)

        metadata_fields = [
            "_id", "fields", "filename", "finished", "time_created",
            "url", "parent_filename"]
        processed_file = file_without_metadata.drop(*metadata_fields)

        return processed_file

    def fields_from_dataframe(self, dataframe, is_string):
        text_fields = []
        first_row = dataframe.first()

        if(is_string):
            for column in dataframe.schema.names:
                if(type(first_row[column]) == str):
                    text_fields.append(column)
        else:
            for column in dataframe.schema.names:
                if(type(first_row[column]) != str):
                    text_fields.append(column)

        return text_fields

    def build_model(self, database_url_training, database_url_test,
                    preprocessor_code, classificators_list):
        training_df = self.file_processor(database_url_training)
        testing_df = self.file_processor(database_url_test)

        preprocessing_variables = locals()
        exec(preprocessor_code, globals(), preprocessing_variables)

        features_training = preprocessing_variables['features_training']
        features_testing = preprocessing_variables['features_testing']
        features_evaluation = preprocessing_variables['features_evaluation']

        classificator_switcher = {
            "lr": LogisticRegression(),
            "dt": DecisionTreeClassifier(),
            "rf": RandomForestClassifier(),
            "gb": GBTClassifier(),
            "nb": NaiveBayes(),
            "svc": LinearSVC()
        }

        for classificator_name in classificators_list:
            classificator = classificator_switcher[classificator_name]
            self.classificator_handler(
                classificator, classificator_name, features_training,
                features_testing, features_evaluation)

        self.spark_session.stop()

    def classificator_handler(self, classificator, classificator_name,
                              features_training, features_testing,
                              features_evaluation):
        classificator.featuresCol = "features"
        classificator.maxIter = 10
        model = classificator.fit(features_training)

        if(features_evaluation is not None):
            evaluation_prediction = model.transform(features_evaluation)
            evaluator = MulticlassClassificationEvaluator(
                labelCol="label",
                predictionCol="prediction",
                metricName="accuracy")

            model_accuracy = evaluator.evaluate(evaluation_prediction)
            print("Accuracy of " + classificator_name + " is = " +
                  str(model_accuracy), flush=True)
            print("Test Error of " + classificator_name + " = " +
                  str((1.0 - model_accuracy)), flush=True)

        testing_prediction = model.transform(features_testing)

        for row in testing_prediction.collect():
            print(row, flush=True)


class MongoOperations(DatabaseInterface):

    def __init__(self, database_url, database_port, database_name):
        self.mongo_client = MongoClient(
            database_url, int(database_port))
        self.database = self.mongo_client[database_name]

    def get_filenames(self):
        return self.database.list_collection_names()

    def find_one(self, filename, query):
        file_collection = self.database[filename]
        return file_collection.find_one(query)


class ModelBuilderRequestValidator(RequestValidatorInterface):
    def __init__(self, database_connector):
        self.database = database_connector

    def training_filename_validator(self, training_filename):
        filenames = self.database.get_filenames()

        if(training_filename not in filenames):
            raise Exception(self.MESSAGE_INVALID_TRAINING_FILENAME)

    def test_filename_validator(self, test_filename):
        filenames = self.database.get_filenames()

        if(test_filename not in filenames):
            raise Exception(self.MESSAGE_INVALID_TEST_FILENAME)

    def model_classificators_validator(self, classificators_list):
        classificator_names_list = ["lr", "dt", "rf", "gb", "nb", "svc"]
        for classificator_name in classificators_list:
            if(classificator_name not in classificator_names_list):
                raise Exception(self.MESSAGE_INVALID_CLASSIFICATOR)
