# proj10-Gcal
A meeting web app. Used to schedule meetings on peoples free times using their appointments in Google Calendar.


## Author: Michal Young ##
### Editor: Jeffrey Knees, jknees@uoregon.edu ###

# Overview
Get appointment data from a selection of a user's Google calendars. Take the data obtained and display the busy times and free times that correspond with in the appointed windows of time.
Then gives the option to share free times with other people so that there free times will show the intersections of free times on the final schedule page. In the end the final schedule page will show the intersecting
free times for everyone so that a meeting can be picked.

# Implementation
Used flask (A python microframework) to impliment a server on my raspberry pi. Used mongodb to store all the variables needed for each session of meetings. I used the meetings as a profile instead of a person.
This makes it much easier to add to the meeting by giving the users the uuid. This references the meeting file in the database and pulls from that. After the user is done adding their freetimes, their files get
stored as the intersection of what is already in the database and what they have. The backend handles most of the inputs from the html like the times and dates. I used two modules to help
with date and time (datetime, arrow). Pymongo was used to deal with the mongo database. The main API used in this project was GoogleCalendars. This was the most important implementation because I used the users
calendar events to make the free times. 

# How to run
* git clone https://github.com/jknees/proj10-Gcal
* cd 'repo'
* make run
* open web browser to localhost:5000

# Tests
* Implemented tests for interpreting time and intersecting agendas.
* make test
