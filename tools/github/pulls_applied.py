#!/usr/bin/env python

import sys
import os
import getpass
import datetime
from github import Github
from github_issues import GithubIssues

gh = Github(login_or_token=raw_input("Enter github username: "),
            password=getpass.getpass('Enter github password: '),
            user_agent='PyGithub/Python')

print "Enter location (<user>/<repo>)",
repo_full_name = 'autotest/virt-test'
repo_full_name = raw_input("or blank for '%s': "
                           % repo_full_name).strip() or repo_full_name

print

issues = GithubIssues(gh, repo_full_name)
print

print "Pull requests applied since:"

while True:
    date_string = "20" + raw_input("Enter date (YY-MM-DD): ") + " 00:00:00.0"
    date_string = date_string.strip()
    fmt = '%Y-%m-%d %H:%M:%S.%f'
    try:
        since = datetime.datetime.strptime(date_string, fmt)
        break
    except ValueError:
        print "When?"
print

print "Enter github labels, blank to end:"
labels = []
while True:
    label = raw_input("labels[%d]" % (len(labels) + 1))
    label = label.strip()
    if label:
        try:
            # http://jacquev6.github.io
            # /PyGithub/github_objects/Label.html#github.Label.Label
            labels.append(issues.get_gh_label(label).name)
        except ValueError, detail:
            print str(detail)
    else:
        break
print

# Search criteria is put into a dictionary
#            state - str - 'open', 'closed'
#            assignee - list of str (login), "none" or "*"
#            mentioned - str (login)
#            labels - list of str (label name)
#            sort - str - 'created', 'updated', 'comments'
#            direction - str - 'asc', 'desc'
#            since - datetime.datetime
criteria = {'state': 'closed', 'labels': labels,
            'sort': 'updated', 'since': since}

heading = ("Applied %s pull-requests from %s since %s  by author"
           % (",".join(labels), repo_full_name, since.isoformat()))
print heading
print "-" * len(heading)
print

author_issues = {}
for number in issues.search(criteria):
    issue = issues[number]
    # Issues don't have commits
    if issue['commits'] is not None:
        author_issues[issue['author']] = issue

authors = author_issues.keys()
authors.sort()
for author in authors:
    issue = author_issues[author]
    print "Pull #%d: '%s'" % (issue['number'], issue['summary'])
    print "    %d commit(s) by %s" % (issue['commits'],
                                      ",".join(issue['commit_authors']))
    print

# make sure cache is cleaned and saved up
del issues

print
