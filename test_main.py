import flask_main
import arrow
from dateutil import tz

def test_interpret_time():
  assert flask_main.interpret_time("10:00 am") == '2016-01-01T10:00:00-08:00'

def test_interpret_date():
  assert flask_main.interpret_date("11/11/2016") == '2016-11-11T00:00:00-08:00'
