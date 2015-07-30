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

for issue in issues:
    sys.stdout.write(str(issue['number']) + '\n')
    sys.stdout.flush()

# make sure cache is cleaned and saved up
del issues

print
