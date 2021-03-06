
import flask
from flask import render_template
from flask import request
from flask import url_for
from flask import session
import uuid

import json
import logging

# Date handling 
import arrow # Replacement for datetime, based on moment.js
import datetime # But we still need time
from dateutil import tz  # For interpreting local times


# OAuth2  - Google library implementation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Google API for services 
from apiclient import discovery

# Mondgo database
from pymongo import MongoClient
import secrets.admin_secrets
import secrets.client_secrets
MONGO_CLIENT_URL = "mongodb://{}:{}@localhost:{}/{}".format(
    secrets.client_secrets.db_user,
    secrets.client_secrets.db_user_pw,
    secrets.admin_secrets.port, 
    secrets.client_secrets.db)

###
# Globals
###
import CONFIG
import secrets.admin_secrets  # Per-machine secrets
import secrets.client_secrets # Per-application secrets
#  Note to CIS 322 students:  client_secrets is what you turn in.
#     You need an admin_secrets, but the grader and I don't use yours. 
#     We use our own admin_secrets file along with your client_secrets
#     file on our Raspberry Pis. 

import agenda # Has all of our class methods for dealing
# with the overlap of appointments and freetimes.

app = flask.Flask(__name__)
app.debug=CONFIG.DEBUG
app.logger.setLevel(logging.DEBUG)
app.secret_key=CONFIG.secret_key

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = secrets.admin_secrets.google_key_file  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'

####
# Database connection per server process
###

try: 
    dbclient = MongoClient(MONGO_CLIENT_URL)
    db = getattr(dbclient, secrets.client_secrets.db)
    collection = db.dated

except:
    print("Failure opening database.  Is Mongo running? Correct password?")
    sys.exit(1)

#############################
#
#  Pages (routed from URLs)
#
#############################

@app.route("/")
@app.route("/index")
def index():
  app.logger.debug("Entering index")
  if 'begin_date' not in flask.session:
    init_session_values()
  return render_template('index.html')

@app.route("/choose")
def choose():
    ## We'll need authorization to list calendars 
    ## I wanted to put what follows into a function, but had
    ## to pull it back here because the redirect has to be a
    ## 'return' 
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.g.calendars = list_calendars(gcal_service)
    return render_template('index.html')

####
#
#  Google calendar authorization:
#      Returns us to the main /choose screen after inserting
#      the calendar_service object in the session state.  May
#      redirect to OAuth server first, and may take multiple
#      trips through the oauth2 callback function.
#
#  Protocol for use ON EACH REQUEST: 
#     First, check for valid credentials
#     If we don't have valid credentials
#         Get credentials (jump to the oauth2 protocol)
#         (redirects back to /choose, this time with credentials)
#     If we do have valid credentials
#         Get the service object
#
#  The final result of successful authorization is a 'service'
#  object.  We use a 'service' object to actually retrieve data
#  from the Google services. Service objects are NOT serializable ---
#  we can't stash one in a cookie.  Instead, on each request we
#  get a fresh serivce object from our credentials, which are
#  serializable. 
#
#  Note that after authorization we always redirect to /choose;
#  If this is unsatisfactory, we'll need a session variable to use
#  as a 'continuation' or 'return address' to use instead. 
#
####

def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value. 
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])

    if (credentials.invalid or
        credentials.access_token_expired):
      return None
    return credentials


def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  ## Note we are *not* redirecting above.  We are noting *where*
  ## we will redirect to, which is this function. 
  
  ## The *second* time we enter here, it's a callback 
  ## with 'code' set in the URL parameter.  If we don't
  ## see that, it must be the first time through, so we
  ## need to do step 1. 
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    return flask.redirect(flask.url_for('choose'))

#####
#
#  Option setting:  Buttons or forms that add some
#     information into session state.  Don't do the
#     computation here; use of the information might
#     depend on what other information we have.
#   Setting an option sends us back to the main display
#      page, where we may put the new information to use. 
#
#####

@app.route('/setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")  
    flask.flash("Date range: '{}'".format(
      request.form.get('daterange')))

    begin_time = request.form.get('begin_time')
    end_time = request.form.get('end_time')
    set_time_range(begin_time, end_time)

    app.logger.debug("SetTimeRange parsed begin and end time as {} - {}".format(flask.session['begin_time'], flask.session['end_time']))

    daterange = request.form.get('daterange')
    set_date_range(daterange)
    
    return flask.redirect(flask.url_for("choose"))

def set_time_range(begin_time, end_time):
  """
  Helper function to set the time range
  Input:
    begin_time: Begin time from form
    end_time: End time from form
  Output:
    None
  Sets the sessions end_time and begin_time to the interpreted time.
  """
  app.logger.debug("Entering setrange")
  flask.flash("Times given: '{}' - '{}'".format(request.form.get('begin_time'), request.form.get('end_time')))
  flask.session["end_time"]= interpret_time(end_time)
  flask.session["begin_time"]= interpret_time(begin_time)

def set_date_range(daterange):
  """
  Helper function to set the date range
  Input:
    daterange: The range of dates given by the datepicker in the html
  Output:
    None
  Modifies the session variables of datarange, begin_date, end_date to display the appropriate interpreted times.
  """
  flask.session['daterange'] = daterange
  daterange_parts = daterange.split()
  flask.session['begin_date'] = interpret_date(daterange_parts[0])
  flask.session['end_date'] = interpret_date(daterange_parts[2])
  app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
    daterange_parts[0], daterange_parts[1], 
    flask.session['begin_date'], flask.session['end_date']))

@app.route('/chooseCal', methods=['POST'])
def chooseCal():
  """
  Called when the user is choosing the calendar they want to use
  Input:
    None
  Output:
    Returns a way to redirect the page to the choose function.
  """
  app.logger.debug("Checking credentials")
  credentials = valid_credentials()
  if not credentials:
    app.logger.debug("Redirecting to authorization")
    return flask.redirect(flask.url_for('oauth2callback'))
  gcal_service = get_gcal_service(credentials)
  app.logger.debug("Returned from get_gcal_service")
  
  # Converts the arrow time objects to datetime to be used for the choosing of events in the given calendars.
  begin_date = arrow.get(flask.session['begin_date'])
  end_date = arrow.get(flask.session['end_date'])
  begin_time = arrow.get(flask.session['begin_time']).datetime.timetz()
  end_time = arrow.get(flask.session['end_time']).datetime.timetz()

  sCal = request.form.getlist('vals') # Obtains values of calendars in html
  events = []
  free_times = agenda.Agenda()
  freeblocks = agenda.Agenda()

  # Gets all of the events in the calendar ranging the dates and not times
  for cal in sCal:
    events.extend(list_events(gcal_service, begin_date.isoformat(), end_date.isoformat(), cal))
  
  # Gets the events from the already gotten events that lie within the time range.
  for e in events:
    if not (arrow.get(e['end_time']).timetz() < begin_time or arrow.get(e['start_time']).timetz() > end_time):
      appt = agenda.Appt(arrow.get(e["start_time"]).datetime.date(), arrow.get(e["start_time"]).datetime.timetz(), arrow.get(e["end_time"]).datetime.timetz(), e["summary"])
      free_times.append(appt)

  day_gap = end_date.datetime.date() - begin_date.datetime.date()
  free_date = begin_date
  for i in range(day_gap.days +1):
    free_date = begin_date.replace(days=+i)
    free_appt = agenda.Appt(free_date.datetime.date(), begin_time, end_time, "free time")
    freeblocks.append(free_appt)

  comp_free = free_times.complement(freeblocks) # Problem with code here
  flash_list = []
  for appt in comp_free:
    flash_list.append(str(appt))

  for appt in free_times:
    flash_list.append(str(appt))

  flash_list.sort()

  session['events'] = flash_list
  
  return flask.redirect(url_for('choose'))

@app.route('/deleteEvents', methods=['POST'])
def deleteEvents():
  """
  Deletes the selected events from the ones chosen in the form. Then inserts them into the database with a uuid.
  Input:
    None
  Output:
    Returns the schedule page with the uuid
  Used only for the maker. Not used for the invitee.
  """
  events = request.form.getlist('vals')
  eventsToBeDeleted = []
  for event in events:
    eventsToBeDeleted.append(session['events'][int(event)])

  for event in eventsToBeDeleted:
    fields = event.split("|")
    if (fields[1].strip() == "free time"):
      session['events'].remove(event)
    else:
      tmp = agenda.Appt.from_string(event)
      tmp.desc = "free time"
      session['events'].remove(event)
      session['events'].append(str(tmp))


  session['uuid'] = str(uuid.uuid4())

  app.logger.debug("session['events'] = {}".format(session['events']))
  removeList = []
  for event in session['events']:
    app.logger.debug("Event: {}".format(event))

  for event in session['events']:
    app.logger.debug("event: {}".format(event))
    fields = event.split("|")
    if not (fields[1].strip() == "free time"):
      app.logger.debug("Removed: {}".format(event))
      removeList.append(event)

  for event in removeList:
    session['events'].remove(event)

  insertToDatabase(session['events'], session['uuid'], session['begin_date'], session['end_date'], session['begin_time'], session['end_time'])

  return flask.redirect(url_for('schedule', uuid = session['uuid']))

def insertToDatabase(events, uuid, begin_date, end_date, begin_time, end_time):
  record = { 'events': events,
             'uuid': uuid,
             'begin_date': begin_date,
             'end_date': end_date,
             'begin_time': begin_time,
             'end_time': end_time
          }

  collection.insert(record)

@app.route('/deleteEventsCombine', methods=['POST'])
def deleteEventsCombine():
  """
  Deletes the selected events from the events chosen in the form. Then itersects them with the events already in the database.
  Input:
    None
  Output:
    Returns url for schedule with the uuid
  Used by the invitee. Because it adds to the database. Does not create.
  """
  events = request.form.getlist('vals')
  eventsToBeDeleted = []
  if len(events) != 0:
    for event in events:
      eventsToBeDeleted.append(session['events'][int(event)])

  for event in eventsToBeDeleted:
    fields = event.split("|")
    if (fields[1].strip() == "free time"):
      session['events'].remove(event)
    else:
      tmp = agenda.Appt.from_string(event)
      tmp.desc = "free time"
      session['events'].remove(event)
      session['events'].append(str(tmp))

  for event in session['events']:
    fields = event.split()
    if (fields[1].strip() != "free time"):
      session['events'].remove(event)

  dataAgenda = setAgendas(session['databaseEvents'], session['events'])

  collection.update({'uuid': session['uuid']}, {"$set":{'events' : str(dataAgenda)}})
  
  return flask.redirect(url_for('schedule', uuid = session['uuid']))

def setAgendas(databaseEvents, events):
  """
  Helper function to intersect agendas
  Input:
    databaseEvents: Free times that are in the database
    events: Free times that the user wants added
  Output:
    Returns the intersected agendas
  """
  curAgenda = agenda.Agenda()
  newAgenda = agenda.Agenda()
  for event in databaseEvents:
    curAgenda.append(agenda.Appt.from_string(event))

  for event in databaseEvents:
    curAgenda.append(agenda.Appt.from_string(event))

  return curAgenda.intersect(newAgenda)


@app.route('/invitee/<uuid>')
def invitee(uuid):
  sessionVariables = collection.find_one({'uuid': uuid})
  session['end_time'] = sessionVariables['end_time']
  session['begin_time'] = sessionVariables['begin_time']
  session['end_date'] = sessionVariables['end_date']
  session['begin_date'] = sessionVariables['begin_date']
  session['databaseEvents'] = sessionVariables['events']
  session['uuid'] = sessionVariables['uuid']
  session['formattedEndTime'] = arrow.get(session['end_time']).format("HH:mm")
  session['formattedBeginTime'] = arrow.get(session['begin_time']).format("HH:mm")

  app.logger.debug(session)
  return(render_template('invitee.html'))

# Needs testing
@app.route('/schedule/<uuid>')
def schedule(uuid):
  sessionVariables = collection.find_one({'uuid': uuid})
  session['end_time'] = sessionVariables['end_time']
  session['begin_time'] = sessionVariables['begin_time']
  session['end_date'] = sessionVariables['end_date']
  session['begin_date'] = sessionVariables['begin_date']
  session['events'] = sessionVariables['events']
  session['uuid'] = sessionVariables['uuid']
  session['formattedEndTime'] = arrow.get(session['end_time']).format("HH:mm")
  session['formattedBeginTime'] = arrow.get(session['begin_time']).format("HH:mm")
  session['url'] = url_for('invitee', uuid= session['uuid'], _external=True)

  return(render_template('schedule.html'))

####
#
#   Initialize session variables 
#
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')     # We really should be using tz from browser
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    flask.session["begin_date"] = tomorrow.floor('day').isoformat()
    flask.session["end_date"] = nextweek.ceil('day').isoformat()
    flask.session["daterange"] = "{} - {}".format(
        tomorrow.format("MM/DD/YYYY"),
        nextweek.format("MM/DD/YYYY"))
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = interpret_time("9am")
    flask.session["end_time"] = interpret_time("5pm")


def interpret_time( text ):
    """
    Read time in a human-compatible format and
    interpret as ISO format with local timezone.
    May throw exception if time can't be interpreted. In that
    case it will also flash a message explaining accepted formats.
    """
    app.logger.debug("Decoding time '{}'".format(text))
    time_formats = ["ha", "h:mma",  "h:mm a", "H:mm", "H a"]
    try: 
        as_arrow = arrow.get(text, time_formats).replace(tzinfo=tz.tzlocal())
        as_arrow = as_arrow.replace(year=2016) #HACK see below
        app.logger.debug("Succeeded interpreting time")
    except:
        app.logger.debug("Failed to interpret time")
        flask.flash("Time '{}' didn't match accepted formats 13:30 or 1:30pm"
              .format(text))
        raise
    return as_arrow.isoformat()
    #HACK #Workaround
    # isoformat() on raspberry Pi does not work for some dates
    # far from now.  It will fail with an overflow from time stamp out
    # of range while checking for daylight savings time.  Workaround is
    # to force the date-time combination into the year 2016, which seems to
    # get the timestamp into a reasonable range. This workaround should be
    # removed when Arrow or Dateutil.tz is fixed.
    # FIXME: Remove the workaround when arrow is fixed (but only after testing
    # on raspberry Pi --- failure is likely due to 32-bit integers on that platform)


def interpret_date( text ):
    """
    Convert text of date to ISO format used internally,
    with the local time zone.
    """
    try:
      as_arrow = arrow.get(text, "MM/DD/YYYY").replace(
          tzinfo=tz.tzlocal())
    except:
        flask.flash("Date '{}' didn't fit expected format 12/31/2001")
        raise
    return as_arrow.isoformat()

def next_day(isotext):
    """
    ISO date + 1 day (used in query to Google calendar)
    """
    as_arrow = arrow.get(isotext)
    return as_arrow.replace(days=+1).isoformat()

####
#
#  Functions (NOT pages) that return some information
#
####
  
def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict.
    The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")  
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]
    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal: 
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]
        

        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)

def list_events(service, begin_time, end_time, calId):
  # FIXME: Maybe make the events into classes here so we can sort and combine them later.
  app.logger.debug("Entering list_events")
  event_list = service.events().list(calendarId=calId, timeMin=begin_time, timeMax=end_time).execute()['items']
  results = []
  # app.logger.debug("Events(in list_events): {}".format(event_list))
  for event in event_list:
    if "transparency" not in event:
      summary = event["summary"]
      start_time = event["start"]["dateTime"]
      end_time = event["end"]["dateTime"]

      results.append(
        { "summary": summary,
          "start_time": start_time,
          "end_time": end_time
          })
  return sorted(results, key=lambda k: k["start_time"])

def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])


#################
#
# Functions used within the templates
#
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try: 
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"
    
#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0")
    