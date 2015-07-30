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

print "Enter github labels, blank to end:"
labels = []
while True:
    label = raw_input("labels[%d]: " % (len(labels) + 1))
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

criteria = {'state': 'open', 'labels': labels,
            'sort': 'updated', 'direction': 'asc'}

heading = ("Oldest updates for Open %s pull requests from %s, past 1 day old:"
           % (",".join(labels), repo_full_name))
print heading
print "-" * len(heading)
print

for number in issues.search(criteria):
    if issues[number]['commits'] and issues[number]['commits'] > 0:
        age = datetime.datetime.now() - issues[number]['modified']
        hours = age.seconds / (60 * 60)
        days = age.days
        url = issues[number]['url']
        summary = issues[number]['summary']
        if days > 0:
            print "%s -  %d days %d hours old - %s" % (
                  url, days, hours, summary[0:30])
        else:
            # Results sorted by decreasing update age
            # don't care about issues updated today
            break

# make sure cache is cleaned and saved up
del issues

print
