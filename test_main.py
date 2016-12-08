import flask_main
import arrow
from dateutil import tz
import dateutil
import uuid
import bson

_id = str(uuid.uuid4())

def test_interpret_time():
	assert flask_main.interpret_time("10:00 am") == '2016-01-01T10:00:00-08:00'

def test_interpret_date():
	assert flask_main.interpret_date("11/11/2016") == '2016-11-11T00:00:00-08:00'

def test_test_insert_database():
	global _id
	begin_date = arrow.get(flask_main.interpret_date('12/04/2016'))
	end_date = arrow.get(flask_main.interpret_date('12/13/2016'))
	begin_time = arrow.get(flask_main.interpret_time('10:00 am')).datetime.timetz()
	end_time = arrow.get(flask_main.interpret_time('10:00 pm')).datetime.timetz()

	flask_main.insertToDatabase(['2016.12.11 10:00 22:00 | free time'], _id, str(begin_date), str(end_date), str(begin_time), str(end_time))
	data = flask_main.collection.find_one({'uuid': uuid})
	assert data['_id'] == _id
	assert data['events'] == '2016.12.11 10:00 22:00 | free time'