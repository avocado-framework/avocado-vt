#!/usr/bin/env python

from __future__ import print_function

import getpass
import sys

from github import Github
from github_issues import GithubIssues
from six.moves import input

gh = Github(
    login_or_token=input("Enter github username: "),
    password=getpass.getpass("Enter github password: "),
    user_agent="PyGithub/Python",
)

print("Enter location (<user>/<repo>)", end=" ")
repo_full_name = "avocado-framework/avocado-vt"
repo_full_name = input("or blank for '%s': " % repo_full_name).strip() or repo_full_name

print()

issues = GithubIssues(gh, repo_full_name)

for issue in issues:
    sys.stdout.write(str(issue["number"]) + "\n")
    sys.stdout.flush()

# make sure cache is cleaned and saved up
del issues

print()
