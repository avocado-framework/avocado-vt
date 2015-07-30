#!/usr/bin/env python

import sys
import os
import getpass
import datetime
from github import Github
from github_issues import GithubIssues, MutableIssue


def set_labels(mutable_issue):
    print "Enter replacement github labels, blank to end:"
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
    if len(labels) > 0:
        mutable_issue['labels'] = labels

gh = Github(login_or_token=raw_input("Enter github username: "),
            password=getpass.getpass('Enter github password: '),
            user_agent='PyGithub/Python')

print "Enter location (<user>/<repo>)",
repo_full_name = 'autotest/virt-test'
repo_full_name = raw_input("or blank for '%s': "
                           % repo_full_name).strip() or repo_full_name
print

issues = GithubIssues(gh, repo_full_name)

# Can't directly search for no labels
criteria = {'state': 'open',
            'sort': 'updated', 'direction': 'asc'}  # updated-asc == oldest first

heading = ("Open, unlabeled issues from %s, oldest-first" % repo_full_name)
print heading
print "-" * len(heading)
print

repo = gh.get_repo(repo_full_name)
labels = ", ".join([label.name for label in repo.get_labels()])

for number in issues.search(criteria):
    if len(issues[number]['labels']) > 0:
        continue
    print '#%d:' % number,
    print issues[number]['summary'] + ':'
    print issues[number]['description']
    print "Available Labels:", labels
    set_labels(MutableIssue(issues, number))

# make sure cache is cleaned and saved up
del issues

print
