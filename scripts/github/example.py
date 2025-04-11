#!/usr/bin/env python

from __future__ import print_function

import datetime
import getpass
import sys

# PyGithub >= 1.13 is required https://pypi.python.org/pypi/PyGithub
from github import Github
from github_issues import GithubIssues, GithubIssuesBase

# You could use OAuth here too for unattended access
# see http://developer.github.com/v3/oauth/#create-a-new-authorization
print("Enter github username:")
username = sys.stdin.readline().strip()
print()
password = getpass.getpass("Enter github password: ")

gh = Github(login_or_token=username, password=password, user_agent="PyGithub/Python")
# needed to fetch fresh rate_limiting data
repo = gh.get_repo("avocado-framework/avocado-vt")

# Requests for logged in users are limited to 5000 per hour
# or about 1 request every 0.7 seconds
start = gh.rate_limiting
# Open up cache and repository
issues = GithubIssues(gh, "avocado-framework/avocado-vt")
print("Issue #125: ", end=" ")
# Any issue can be referenced by number
print(issues[125])
end = gh.rate_limiting
print("Requests used: ", start[0] - end[0])
print("Cache hits: %s misses: %s" % (issues.cache_hits, issues.cache_misses))

# Pull requests are treated as issues
issues = GithubIssues(gh, "avocado-framework/avocado-vt")
start = end
print("Pull #526: ", end=" ")
print(issues[526])
end = gh.rate_limiting
print("Requests used: ", start[0] - end[0])
print("Cache hits: %s misses: %s" % (issues.cache_hits, issues.cache_misses))

# Listing issues requires finding the last issue
# this takes a while when the cache is empty
issues = GithubIssues(gh, "avocado-framework/avocado-vt")
start = end
print("Total number of issues (this could take a while):")
# This len() is used to force the slower binary-search
print(GithubIssuesBase.__len__(issues))
end = gh.rate_limiting
print("Requests used: ", start[0] - end[0])
print("Cache hits: %s misses: %s" % (issues.cache_hits, issues.cache_misses))

# Searches are supported and return lists of issue-numbers
issues = GithubIssues(gh, "avocado-framework/avocado-vt")
start = end
print("Open issues last few days without any label (could take 2-10 minutes):")
two_days = datetime.timedelta(days=2)
last_week = datetime.datetime.now() - two_days
# Search criteria is put into a dictionary
#            state - str - 'open', 'closed'
#            assignee - list of str (login), "none" or "*"
#            mentioned - str (login)
#            labels - list of str (label name)
#            sort - str - 'created', 'updated', 'comments'
#            direction - str - 'asc', 'desc'
#            since - datetime.datetime
criteria = {"state": "open", "since": last_week}
# Search results are cached for 10-minutes, otherwise searches can be slow
for number in issues.search(criteria):
    issue = issues[number]
    # some items must be searched/compared manually
    if len(issue["labels"]) < 1:
        print(
            'https://github.com/avocado-framework/avocado-vt/issues/%s\t"%s"'
            % (issue["number"], issue["summary"])
        )
print()
print("Requests used: ", start[0] - end[0])
print("Cache hits: %s misses: %s" % (issues.cache_hits, issues.cache_misses))

# Now that cache is populated, this will be very fast
issues = GithubIssues(gh, "avocado-framework/avocado-vt")
start = end
print("Total number of issues (this should be a lot faster):")
# This length uses a cached issue count plus a 'since' criteria search
print(len(issues))
end = gh.rate_limiting
print("Final Requests used: ", start[0] - end[0])
print("Cache hits: %s misses: %s" % (issues.cache_hits, issues.cache_misses))
del issues
