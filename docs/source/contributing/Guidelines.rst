=================================
Contributions Guidelines and Tips
=================================

Code
====

Contributions of additional tests and code are always welcome. If in
doubt, and/or for advice on approaching a particular problem, please
contact the projects members (see section _collaboration) Before submitting code,
please review the `git repository configuration guidelines <https://autotest.readthedocs.io/en/latest/main/developer/GitWorkflow.html>`_.

To submit changes, please follow `these instructions <https://autotest.readthedocs.io/en/latest/main/developer/SubmissionChecklist.html>`_.
Please allow up to two weeks for a maintainer to pick
up and review your changes.  Though, if you'd like help at any stage, feel free to post on the mailing
lists and reference your pull request.

Docs
====

Please edit the documentation directly to correct any minor inaccuracies
or to clarify items. The preferred markup syntax is
`ReStructuredText <http://en.wikipedia.org/wiki/ReStructuredText>`_,
keeping with the conventions and style found in existing documentation.
For any graphics or diagrams, web-friendly formats should be used, such as
PNG or SVG.

Avoid using 'you', 'we', 'they', as they can be ambiguous in reference
documentation.  It works fine in conversation and e-mail, but looks weird
in reference material. Similarly, avoid using 'unnecessary', off-topic, or
extra language. For example in American English, `"Rinse and repeat" 
<http://en.wikipedia.org/wiki/Lather,_rinse,_repeat>`_ is a funny phrase,
but could cause problems when translated into other languages. Basically,
try to avoid anything that slows the reader down from finding facts.

Rules for Reviewers
===================

1. Everyone who has experiences in the project is encouraged to review PRs.
2. Respectful, kind, patient to the coders
3. Freely deny for changes the codebase does not want/need even though
   perfect design/codes
4. Ask questions rather than make statements.
5. Not encourage the “Why” questions. Good practice: e.g. Wouldn't it make more sense to
   Would you like to? Could you give the reason that ...?
6. Remember to praise.
7. Remember that there is often more than one way to approach a solution.
8. Given clear and useful comments, and explain the reason why reqest change
9. In general, reviewers should favor approving a PR once it is in a
   state where it definitely improves the overall code health of the
   system being worked on, even if the PR isn't perfect
   (maintainability, readability, and understandability).
10. Share your best practice/knowledge as a mentor.
11. Cautiously regard personal preference as best practice and impose
    to contributors
12. Dismiss your approval if you add new comment for a PR after you
    already have given an approval
13. It is ok to use a 'request review' tool to ask someone to review
    as you like, but not a must.
14. It is ok to cancel the request review to you if you think you are
    not a suitable one for this PR.
15. Wait for request review for no more than 2 weeks on those PRs
    which have already 2 approvals

Rules for Maintainers
=====================

1. Includes all reviewer's rules
2. Make sure all PRs submitted can be closed within 3 months
3. Generally every PR needs at least 1 maintainer’s approval and total
   2 approvals before being merged.
 a) Add request for review for more maintainers if there is a need
 b) Add a comment to explain why a PR need the label 'request_2_maintainers'
4. Mark proper and necessary labels according to the information provided by the PR contributor
5. Closing a PR threshold:no response from contributor after 1 month, the PR will be labelled as, "No response" and after 3 months it will be closed

Rules for Contributors
======================

1. [Must] Coding style should conform to what's enforced by black (see ``./avocado-static-checks/check-style``)
2. [Must] PR commit message is meaningful. Refer to the link on how to write a good commit message
3. [Must] Travis CI pass and no conflict
4. [Must] Provide test results. If no, provide justification. Apply to any PR
  One of below options should be aligned:
5. [Must] If the function defined with right docstring (description and params, and return if have)
6. [Must] If the PR depends on other PRs, please add a comment to say if your PR has a dependence in order to ensure the PR is merged after dependence PRs
7. [Must] If the API of one library is changed, ask for all test cases to be modified which invoke this library and provide test results of representative test cases.
8. [Must] If the case does some package version judgement for the new case support or compatible backwards
9. [Must] If the test code have suitable env backup and recovery steps
10. [Optional] If have the necessary and clear comments for the code explanation for steps
11. [Optional] If the case is applied to multiple arches.
12. [Optional] If have duplication, need to create new function or reuse existing library in avocado/avocado-vt
13. [Optional] If the logic are complete and no important branches which are not dealt with
14. [Optional] If the code seems clear and concise, define functions to increase the readability
15. [Optional] Use python supported library instead of shell cmd running by process.run if possible
16. [Optional] If the feature test related aspects are correct
17. [Optional] Add comments to ask questions which you do not understand
18. [Optional] Pay more attention to ‘test.fail(xxx)’ or exception raise part, such as if there is log info
19. [Optional] Reply to the comment when you have fixed the comment (see good sample in Appendix.4)
20. [Optional] Better to use @Someone to ask for review when your PR is submitted
21. [Optional] Use ‘request review’ to ask the original reviewer to request again when you finish updates
