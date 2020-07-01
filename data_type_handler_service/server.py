from flask import jsonify, Flask
import os
from flask_cors import CORS
from data_type_handler import (
    MongoOperations,
    DataTypeHandlerRequestValidator,
    DataTypeConverter)

HTTP_STATUS_CODE_SUCESS = 200
HTTP_STATUS_CODE_SUCESS_CREATED = 201
HTTP_STATUS_CODE_NOT_ACCEPTABLE = 406
HTTP_STATUS_CODE_CONFLICT = 409

DATA_TYPE_HANDLER_HOST = "DATA_TYPE_HANDLER_HOST"
DATA_TYPE_HANDLER_PORT = "DATA_TYPE_HANDLER_PORT"

MESSAGE_RESULT = "result"

FILENAME_NAME = "filename"

FIRST_ARGUMENT = 0

MESSAGE_INVALID_URL = "invalid_url"
MESSAGE_DUPLICATE_FILE = "duplicate_file"
MESSAGE_CHANGED_FILE = "file_changed"
MESSAGE_DELETED_FILE = "deleted_file"

DATABASE_URL = "DATABASE_URL"
DATABASE_PORT = "DATABASE_PORT"
DATABASE_NAME = "DATABASE_NAME"
DATABASE_REPLICA_SET = "DATABASE_REPLICA_SET"

FIELDS_NAME = "fields"

GET = 'GET'
POST = 'POST'
DELETE = 'DELETE'

app = Flask(__name__)
CORS(app)


def collection_database_url(database_url, database_name, database_filename,
                            database_replica_set):
    return database_url + '/' + \
        database_name + '.' + \
        database_filename + "?replicaSet=" + \
        database_replica_set + \
        "&authSource=admin"


@app.route('/type', methods=[POST])
def change_data_type():
    database = MongoOperations(
        os.environ[DATABASE_URL] + '/?replicaSet=' +
        os.environ[DATABASE_REPLICA_SET], os.environ[DATABASE_PORT],
        os.environ[DATABASE_NAME])

    request_validator = DataTypeHandlerRequestValidator(database)

    try:
        request_validator.filename_validator(
            request.json[FILENAME_NAME])
    except Exception as invalid_filename:
        return jsonify(
            {MESSAGE_RESULT:
                invalid_filename.args[FIRST_ARGUMENT]}),\
            HTTP_STATUS_CODE_NOT_ACCEPTABLE

    try:
        request_validator.fields_validator(
            request.json[FILENAME_NAME], request.json[FIELDS_NAME])
    except Exception as invalid_fields:
        return jsonify(
            {MESSAGE_RESULT: invalid_fields.args[FIRST_ARGUMENT]}),\
            HTTP_STATUS_CODE_NOT_ACCEPTABLE

    data_type_converter = DataTypeConverter(database)
    data_type_converter.file_converter(
        request.json[FILENAME_NAME], request.json[FIELDS_NAME])

    return jsonify({MESSAGE_RESULT: MESSAGE_CHANGED_FILE}), \
        HTTP_STATUS_CODE_SUCESS


if __name__ == "__main__":
    app.run(host=os.environ[DATA_TYPE_HANDLER_HOST],
            port=int(os.environ[DATA_TYPE_HANDLER_PORT]))