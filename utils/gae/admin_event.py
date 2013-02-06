# Event Administration pages.
# coding=utf-8
import datetime
import hashlib

from google.appengine.api import users

import schema
import throttled_mail_sender
import webapp_generic

DEFAULT_CAPACITY = 30

class NewEvent(webapp_generic.WebAppGenericProcessor):
    """Form to create a new event."""
    def get(self):
        template_values = {
            'nickname': users.get_current_user().nickname(),
            'eventid': "na", # set it to N/A to later set it to something else...?
            'new_entry': True,
            'capacity': DEFAULT_CAPACITY,
            }
        self.template_render_output(template_values, 'EditEvent.html')

class EditEvent(webapp_generic.WebAppGenericProcessor):
    """Load from the existing data and edit the event"""
    def get(self):
        eventid = self.request.get('eventid')
        event = self.event_cache.get_uncached(eventid)
        if event == None:
            self.http_error_message('Event id %s not found' % (eventid))
            return
        if not self.check_auth_owner(event):
            self.http_error_message('Not your event')
            return

        if event.capacity:
            capacity = event.capacity
        else:
            capacity = 0 # rather than None.

        template_values = {
            'nickname': event.owner.nickname(), # the owner might be not me.
            'owners_email': (','.join(event.owners_email)),
            'eventid': event.eventid,
            'title': event.title,
            'location': event.location,
            'content_text': event.content_text,
            'content_url': event.content_url,
            'prework_text': event.prework_text,
            'event_date': event.event_date,
            'capacity': capacity,
            'new_entry': False
            }
        self.template_render_output(template_values, 'EditEvent.html')


def generate_eventid(event_title, username, time):
    """Create a sha1 hash hex string to use as event ID."""
    sourcestring = event_title + username + time
    h = hashlib.sha1()
    h.update(sourcestring.encode('utf-8'))
    return h.hexdigest()


def timedelta_to_second(timedelta):
    """Convert timedelta to total seconds because total_seconds() is
    not supported before 2.7 and we're using older version of python
    on appengine for now."""
    return timedelta.seconds + timedelta.days * 86400


class RegisterEvent(webapp_generic.WebAppGenericProcessor):
    """Load from the existing database and edit the event content.
    Handler for /eventadmin/register
    """
    def post(self):
        eventid = self.request.get('eventid')
        title = self.request.get('title')
        user = users.get_current_user()

        if eventid == 'na':
            # if it's new, create a new item
            event = schema.Event()
            eventid = generate_eventid(title, user.email(), datetime.datetime.now().isoformat(' '))
            event.eventid = eventid
            event.owner = user
        else:
            event = self.event_cache.get_uncached(eventid)
            if event == None:
                self.http_error_message('Event id %s not found' % (eventid))
                return
            if not self.check_auth_owner(event):
                self.http_error_message('Not your event')
                return

        event.eventid = eventid
        event.owners_email = self.request.get('owners_email').split(',')
        event.title = title
        event.location = self.request.get('location')
        event.content_text = self.request.get('content')
        event.content_url = self.request.get('content_url')
        event.prework_text = self.request.get('prework')
        event.event_date = self.request.get('event_date')
        event.capacity = int(self.request.get('capacity'))
        event.put()
        self.event_cache.invalidate_cache(eventid)

        mail_title = "[Debian登録システム] イベント %s が更新されました" % event.title.encode('utf-8')
        mail_template = {
            'event': event,
            'event_url': 'http://%s/eventadmin/edit?eventid=%s' % (
                self.request.host, eventid),
            }
        mail_message = self.template_render(mail_template, 'RegisterEvent.txt')

        throttled_mail_sender.send_mail(eventid, user.email(), mail_title, mail_message)
        self.redirect('/thanks?eventid=%s' % eventid)


NUM_BUCKETS = 10
WIDTH = 500
HEIGHT = 100
def get_bucket_delta_seconds(delta_seconds):
    """Take an array of delta seconds, and bucket them as histogram
    for output.

    returns an array of index, frequency and bucket representative value."""
    min_delta_seconds = min(delta_seconds)
    max_delta_seconds = max(delta_seconds)
    time_range = max_delta_seconds - min_delta_seconds

    # If there's no range, I can't bucket it.
    if time_range == 0:
        return []

    bucket_interval = (time_range + 1) / float(NUM_BUCKETS)
    bucketed_frequency = [0] * NUM_BUCKETS
    for delta_second in delta_seconds:
        bucket = int((delta_second - min_delta_seconds) / bucket_interval)
        bucketed_frequency[bucket] += 1
    max_bucketed_frequency = max(bucketed_frequency)

    return [{ 'index': i, 
              'frequency': frequency, 
              'bucket': i * bucket_interval + min_delta_seconds,
              'x': i * (WIDTH / NUM_BUCKETS),
              'y': HEIGHT - (frequency / max_bucketed_frequency) * HEIGHT,
              } for i, frequency in enumerate(bucketed_frequency)]


class ViewEventSummary(webapp_generic.WebAppGenericProcessor):
    """View summary of registered users for a given event."""
    def get(self):
        eventid = self.request.get('eventid')
        event = self.event_cache.get_cached(eventid)
        if not event:
            self.http_error_message('Event id %s not found' % (eventid))
            return
        if not self.check_auth_owner(event):
            self.http_error_message("""
You are not allowed to see a summary""")
            return

        attendances, num_attend, num_enkai_attend = self.load_users_with_eventid(eventid)

        # Normalize timestamp to time since event was created; let's see if that's a useful signal to look at.
        bucket_delta_seconds = get_bucket_delta_seconds(
            [timedelta_to_second(
                attendance.timestamp - event.timestamp)
             for attendance in attendances])

        template_values = {
            'eventid': eventid,
            'attendances': attendances,
            'num_attend': num_attend,
            'num_enkai_attend': num_enkai_attend,
            'bucket_delta_seconds': bucket_delta_seconds,
            }

        self.template_render_output(template_values, 'ViewEventSummary.html')


class PreworkLatex(webapp_generic.WebAppGenericProcessor):
    """View prework from registered users in LaTeX format."""
    def get(self):
        eventid = self.request.get('eventid')
        event = self.event_cache.get_cached(eventid)
        if not event:
            self.http_error_message('Event id %s not found' % (eventid))
            return
        if not self.check_auth_owner(event):
            self.http_error_message("""
You are not allowed to see a summary""")
            return

        attendances, num_attend, num_enkai_attend = self.load_users_with_eventid(eventid)

        escaped_attendances = [
            { 'user_realname': attendance.user_realname.replace('_', '\_{}'),
              'prework_text': attendance.prework_text.replace('_', '\_{}'),
              } for attendance in attendances]

        template_values = {
            'attendances': escaped_attendances,
            'num_attend': num_attend,
            'num_enkai_attend': num_enkai_attend,
            }

        self.response.headers['Content-type'] = 'text/plain; charset=utf-8'
        self.template_render_output(template_values, 'PreworkLatex.txt')
