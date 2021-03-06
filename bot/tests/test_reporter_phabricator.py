# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import unittest
import urllib

import pytest
import responses

from code_review_bot import Level

VALID_CLANG_TIDY_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by clang-tidy

You can run this analysis locally with:
 - `./mach static-analysis check another_test.cpp` (C/C++)

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""

VALID_CLANG_FORMAT_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by clang-format

You can run this analysis locally with:
 - `./mach clang-format -s -p dom/test.cpp` (C/C++)

For your convenience, [here is a patch]({results}/clang-format-PHID-DIFF-test.diff) that fixes all the clang-format defects (use it in your repository with `hg import` or `git apply -p0`).

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""


VALID_FLAKE8_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by mozlint-py-flake8

You can run this analysis locally with:
 - `./mach lint --warnings path/to/file` (JS/Python/etc)

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""


VALID_COVERAGE_MESSAGE = """
In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
 - [path/to/test.cpp](https://coverage.moz.tools/#revision=latest&path=path%2Fto%2Ftest.cpp&view=file)

Should they have tests, or are they dead code ?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""

VALID_DEFAULT_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by full-file-analyzer

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""

VALID_TASK_FAILURES_MESSAGE = """
The analysis task [mock-infer](https://treeherder.mozilla.org/#/jobs?revision=aabbccddee&selectedJob=1234) failed, but we could not detect any issue.
Please check this task manually.

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""


VALID_MOZLINT_MESSAGE = """
Code analysis found 2 defects in the diff 42:
 - 2 defects found by mozlint-dummy

You can run this analysis locally with:
 - `./mach lint --warnings path/to/file` (JS/Python/etc)

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""


def test_phabricator_clang_tidy(mock_phabricator, mock_try_task):
    """
    Test Phabricator reporter publication on a mock clang-tidy issue
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details == {
            "revision_id": 51,
            "message": VALID_CLANG_TIDY_MESSAGE,
            "attach_inlines": 1,
            "__conduit__": {"token": "deadbeef"},
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "clang-tidy"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "another_test.cpp": [41, 42, 43]
        }
        revision.files = ["another_test.cpp"]
        reporter = PhabricatorReporter({"analyzers": ["clang-tidy"]}, api=api)

    issue = ClangTidyIssue(
        "source-test-clang-tidy",
        revision,
        "another_test.cpp",
        "42",
        "51",
        "modernize-use-nullptr",
        "dummy message",
    )
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == "http://phabricator.test/api/differential.createcomment"
    assert call.response.headers.get("unittest") == "clang-tidy"


def test_phabricator_clang_format(mock_config, mock_phabricator, mock_try_task):
    """
    Test Phabricator reporter publication on a mock clang-format issue
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision, ImprovementPatch
    from code_review_bot.tasks.clang_format import ClangFormatIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details["message"] == VALID_CLANG_FORMAT_MESSAGE.format(
            results=mock_config.taskcluster.results_dir
        )

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "clang-format"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.cpp": [41, 42, 43],
            "dom/test.cpp": [42],
        }
        reporter = PhabricatorReporter({"analyzers": ["clang-format"]}, api=api)

    issue = ClangFormatIssue(
        "source-test-clang-format", "dom/test.cpp", 42, 1, revision
    )
    assert issue.is_publishable()

    revision.improvement_patches = [
        ImprovementPatch("clang-format", repr(revision), "Some lint fixes")
    ]
    list(map(lambda p: p.write(), revision.improvement_patches))  # trigger local write

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 1

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == "http://phabricator.test/api/differential.createcomment"
    assert call.response.headers.get("unittest") == "clang-format"


@pytest.mark.parametrize(
    "reporter_config, errors_reported",
    [({"publish_errors": True}, True), ({"publish_errors": False}, False), ({}, False)],
)
def test_phabricator_mozlint(
    reporter_config, errors_reported, mock_config, mock_phabricator, mock_try_task
):
    """
    Test Phabricator reporter publication on a mock mozlint issue
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision
    from code_review_bot.tasks.lint import MozLintIssue

    def _check_inline(request):
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])

        assert details == {
            "__conduit__": {"token": "deadbeef"},
            "content": "Error: A bad bad error [flake8: EXXX]",
            "diffID": 42,
            "filePath": "python/test.py",
            "isNewFile": 1,
            "lineLength": 0,
            "lineNumber": 42,
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": {"id": "PHID-XXXX-YYYYY"}}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "flake8-inline"},
            json.dumps(resp),
        )

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details["message"] == VALID_FLAKE8_MESSAGE.format(
            results=mock_config.taskcluster.results_dir
        )

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "flake8-comment"},
            json.dumps(resp),
        )

    def _check_message(request):
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details == {
            "buildTargetPHID": "PHID-HMBT-test",
            "lint": [
                {
                    "char": 1,
                    "code": "EXXX",
                    "description": "A bad bad error",
                    "line": 42,
                    "name": "source-test-mozlint-py-flake8",
                    "path": "python/test.py",
                    "severity": "error",
                }
            ],
            "unit": [],
            "type": "work",
            "__conduit__": {"token": "deadbeef"},
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "flake8-error"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createinline",
        callback=_check_inline,
    )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment,
    )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/harbormaster.sendmessage",
        callback=_check_message,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "python/test.py": [41, 42, 43],
            "dom/test.cpp": [42],
        }
        revision.files = revision.lines.keys()
        reporter = PhabricatorReporter(reporter_config, api=api)

    issue = MozLintIssue(
        analyzer="source-test-mozlint-py-flake8",
        path="python/test.py",
        lineno=42,
        column=1,
        message="A bad bad error",
        level="error",
        revision=revision,
        linter="flake8",
        check="EXXX",
    )
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the callbacks have been used to publish either:
    # - an inline comment + summary comment when publish_errors is False
    # - a lint result + summary comment when publish_errors is True
    assert len(responses.calls) > 0
    if errors_reported:
        urls = [
            "http://phabricator.test/api/differential.createcomment",
            "http://phabricator.test/api/harbormaster.sendmessage",
        ]
        markers = ["flake8-comment", "flake8-error"]

    else:
        urls = [
            "http://phabricator.test/api/differential.createinline",
            "http://phabricator.test/api/differential.createcomment",
        ]
        markers = ["flake8-inline", "flake8-comment"]

    assert [r.request.url for r in responses.calls[-2:]] == urls
    assert [r.response.headers.get("unittest") for r in responses.calls[-2:]] == markers


def test_phabricator_coverage(mock_config, mock_phabricator, mock_try_task):
    """
    Test Phabricator reporter publication on a mock coverage issue
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision
    from code_review_bot.tasks.coverage import CoverageIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details["message"] == VALID_COVERAGE_MESSAGE

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "coverage"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "dom/test.cpp": [42],
        }
        reporter = PhabricatorReporter({"analyzers": ["coverage"]}, api=api)

    issue = CoverageIssue("path/to/test.cpp", 0, "This file is uncovered", revision)
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == "http://phabricator.test/api/differential.createcomment"
    assert call.response.headers.get("unittest") == "coverage"


def test_phabricator_clang_tidy_and_coverage(
    mock_config, mock_phabricator, mock_try_task
):
    """
    Test Phabricator reporter publication on a mock coverage issue
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision
    from code_review_bot.tasks.coverage import CoverageIssue
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    def _check_comment_sa(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details == {
            "revision_id": 51,
            "message": VALID_CLANG_TIDY_MESSAGE,
            "attach_inlines": 1,
            "__conduit__": {"token": "deadbeef"},
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "clang-tidy"},
            json.dumps(resp),
        )

    def _check_comment_ccov(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details["message"] == VALID_COVERAGE_MESSAGE

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "coverage"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment_sa,
    )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment_ccov,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "another_test.cpp": [41, 42, 43],
        }
        revision.files = ["test.txt", "test.cpp", "another_test.cpp"]
        reporter = PhabricatorReporter(
            {"analyzers": ["coverage", "clang-tidy"]}, api=api
        )

    issue_clang_tidy = ClangTidyIssue(
        "source-test-clang-tidy",
        revision,
        "another_test.cpp",
        "42",
        "51",
        "modernize-use-nullptr",
        "dummy message",
    )
    assert issue_clang_tidy.is_publishable()

    issue_coverage = CoverageIssue(
        "path/to/test.cpp", 0, "This file is uncovered", revision
    )
    assert issue_coverage.is_publishable()

    issues, patches = reporter.publish([issue_clang_tidy, issue_coverage], revision, [])
    assert len(issues) == 2
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-2]
    assert call.request.url == "http://phabricator.test/api/differential.createcomment"
    assert call.response.headers.get("unittest") == "clang-tidy"

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == "http://phabricator.test/api/differential.createcomment"
    assert call.response.headers.get("unittest") == "coverage"


def test_phabricator_analyzers(mock_config, mock_phabricator, mock_try_task):
    """
    Test analyzers filtering on phabricator reporter
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision, ImprovementPatch
    from code_review_bot.tasks.clang_format import ClangFormatIssue
    from code_review_bot.tasks.infer import InferIssue
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue
    from code_review_bot.tasks.lint import MozLintIssue
    from code_review_bot.tasks.coverage import CoverageIssue

    def _test_reporter(api, analyzers_skipped):
        # Always use the same setup, only varies the analyzers
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {"test.cpp": [0, 41, 42, 43], "dom/test.cpp": [42]}
        reporter = PhabricatorReporter(
            {"analyzers_skipped": analyzers_skipped}, api=api
        )

        issues = [
            ClangFormatIssue("mock-clang-format", "dom/test.cpp", 42, 1, revision),
            ClangTidyIssue(
                "mock-clang-tidy",
                revision,
                "test.cpp",
                "42",
                "51",
                "modernize-use-nullptr",
                "dummy message",
            ),
            InferIssue(
                "mock-infer",
                {
                    "file": "test.cpp",
                    "line": 42,
                    "column": 1,
                    "bug_type": "dummy",
                    "kind": "WARNING",
                    "qualifier": "dummy message.",
                },
                revision,
            ),
            MozLintIssue(
                "mock-lint-flake8",
                "test.cpp",
                1,
                "error",
                42,
                "flake8",
                "Python error",
                "EXXX",
                revision,
            ),
            CoverageIssue("test.cpp", 0, "This file is uncovered", revision),
        ]

        assert all(i.is_publishable() for i in issues)

        revision.improvement_patches = [
            ImprovementPatch("dummy", repr(revision), "Whatever"),
            ImprovementPatch("mock-clang-tidy", repr(revision), "Some C fixes"),
            ImprovementPatch("mock-clang-format", repr(revision), "Some lint fixes"),
            ImprovementPatch("mock-infer", repr(revision), "Some java fixes"),
            ImprovementPatch("mock-lint-flake8", repr(revision), "Some js fixes"),
        ]
        list(
            map(lambda p: p.write(), revision.improvement_patches)
        )  # trigger local write

        return reporter.publish(issues, revision, [])

    # Use same instance of api
    with mock_phabricator as api:

        # Skip commenting on phabricator
        # we only care about filtering issues
        api.comment = unittest.mock.Mock(return_value=True)

        # All of them
        issues, patches = _test_reporter(api, [])
        assert len(issues) == 5
        assert len(patches) == 5
        assert [i.analyzer for i in issues] == [
            "mock-clang-format",
            "mock-clang-tidy",
            "mock-infer",
            "mock-lint-flake8",
            "coverage",
        ]
        assert [p.analyzer for p in patches] == [
            "dummy",
            "mock-clang-tidy",
            "mock-clang-format",
            "mock-infer",
            "mock-lint-flake8",
        ]

        # Skip clang-tidy
        issues, patches = _test_reporter(api, ["mock-clang-tidy"])
        assert len(issues) == 4
        assert len(patches) == 4
        assert [i.analyzer for i in issues] == [
            "mock-clang-format",
            "mock-infer",
            "mock-lint-flake8",
            "coverage",
        ]
        assert [p.analyzer for p in patches] == [
            "dummy",
            "mock-clang-format",
            "mock-infer",
            "mock-lint-flake8",
        ]

        # Skip clang-tidy and mozlint
        issues, patches = _test_reporter(api, ["mock-clang-format", "mock-clang-tidy"])
        assert len(issues) == 3
        assert len(patches) == 3
        assert [i.analyzer for i in issues] == [
            "mock-infer",
            "mock-lint-flake8",
            "coverage",
        ]
        assert [p.analyzer for p in patches] == [
            "dummy",
            "mock-infer",
            "mock-lint-flake8",
        ]


def test_phabricator_unitresult(mock_phabricator, mock_try_task):
    """
    Test Phabricator UnitResult for a CoverityIssue
    """
    from code_review_bot.tasks.coverity import CoverityIssue
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision

    def _check_message(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details == {
            "buildTargetPHID": "PHID-HMBD-deadbeef12456",
            "lint": [],
            "unit": [
                {
                    "details": 'Code review bot found a **build error**: \nDereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".',
                    "format": "remarkup",
                    "name": "general",
                    "namespace": "code-review",
                    "result": "fail",
                }
            ],
            "type": "work",
            "__conduit__": {"token": "deadbeef"},
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "coverity"},
            json.dumps(resp),
        )

    # Catch the publication of a UnitResult failure
    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/harbormaster.sendmessage",
        callback=_check_message,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.cpp": [41, 42, 43]
        }
        revision.build_target_phid = "PHID-HMBD-deadbeef12456"
        reporter = PhabricatorReporter(
            {"analyzers": ["coverity"], "publish_build_errors": True}, api=api
        )

        issue_dict = {
            "line": 41,
            "reliability": "medium",
            "message": 'Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".',
            "flag": "NULL_RETURNS",
            "build_error": True,
            "extra": {
                "category": "Null pointer dereferences",
                "stateOnServer": {
                    "ownerLdapServerName": "local",
                    "stream": "Firefox",
                    "cid": 95687,
                    "cached": False,
                    "retrievalDateTime": "2019-05-13T10:20:22+00:00",
                    "firstDetectedDateTime": "2019-04-08T12:57:07+00:00",
                    "presentInReferenceSnapshot": False,
                    "components": ["js"],
                    "customTriage": {},
                    "triage": {
                        "fixTarget": "Untargeted",
                        "severity": "Unspecified",
                        "classification": "Unclassified",
                        "owner": "try",
                        "legacy": "False",
                        "action": "Undecided",
                        "externalReference": "",
                    },
                },
            },
        }

        issue = CoverityIssue("mock-coverity", revision, issue_dict, "test.cpp")
        assert issue.is_publishable()

        issues, patches = reporter.publish([issue], revision, [])
        assert len(issues) == 1
        assert len(patches) == 0

        # Check the callback has been used
        assert len(responses.calls) > 0

        # Only check the last call
        print(responses.calls[-1].request.url)
        assert responses.calls[-1].response.headers.get("unittest") == "coverity"


def test_full_file(mock_config, mock_phabricator, mock_try_task):
    """
    Test Phabricator reporter supports an issue on a full file
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision
    from code_review_bot.tasks.default import DefaultIssue

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details["message"] == VALID_DEFAULT_MESSAGE.format(
            results=mock_config.taskcluster.results_dir
        )

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "full-file-comment"},
            json.dumps(resp),
        )

    def _check_inline(request):
        # Check the inline does not have a null value for line
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])

        assert details == {
            "__conduit__": {"token": "deadbeef"},
            "content": "Warning: Something bad happened on the whole file ! [a-huge-issue]",
            "diffID": 42,
            "filePath": "xx.cpp",
            "isNewFile": 1,
            "lineLength": -1,
            # Cannot be null for a full file as it's not supported by phabricator
            "lineNumber": 1,
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": {"id": "PHID-XXXX-YYYYY"}}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "full-file-inline"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createinline",
        callback=_check_inline,
    )
    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "xx.cpp": [123, 124, 125]
        }
        revision.files = list(revision.lines.keys())
        reporter = PhabricatorReporter(api=api)

    issue = DefaultIssue(
        analyzer="full-file-analyzer",
        revision=revision,
        path="xx.cpp",
        line=-1,
        nb_lines=0,
        check="a-huge-issue",
        message="Something bad happened on the whole file !",
    )
    assert issue.line is None  # check auto conversion
    assert (
        str(issue) == "full-file-analyzer issue a-huge-issue@warning xx.cpp full file"
    )
    assert issue.is_publishable()
    assert revision.has_file(issue.path)
    assert revision.contains(issue)

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the comment callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == "http://phabricator.test/api/differential.createcomment"
    assert call.response.headers.get("unittest") == "full-file-comment"

    # Check the inline callback has been used
    call = responses.calls[-2]
    assert call.request.url == "http://phabricator.test/api/differential.createinline"
    assert call.response.headers.get("unittest") == "full-file-inline"


def test_task_failures(mock_phabricator, mock_try_task, mock_treeherder):
    """
    Test Phabricator reporter publication with some task failures
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision
    from code_review_bot.tasks.clang_tidy import ClangTidyTask

    def _check_comment(request):
        # Check the Phabricator main comment is well formed
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details == {
            "revision_id": 51,
            "message": VALID_TASK_FAILURES_MESSAGE,
            "attach_inlines": 1,
            "__conduit__": {"token": "deadbeef"},
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "task-failure"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "aabbccddee"
        reporter = PhabricatorReporter({"analyzers": ["clang-tidy"]}, api=api)

    status = {
        "task": {"metadata": {"name": "mock-infer"}},
        "status": {"runs": [{"runId": 0}]},
    }
    task = ClangTidyTask("ab3NrysvSZyEwsOHL2MZfw", status)
    issues, patches = reporter.publish([], revision, [task])
    assert len(issues) == 0
    assert len(patches) == 0

    # Check the callback has been used
    assert len(responses.calls) > 0
    call = responses.calls[-1]
    assert call.request.url == "http://phabricator.test/api/differential.createcomment"
    assert call.response.headers.get("unittest") == "task-failure"


@pytest.mark.parametrize(
    "reporter_config, errors_reported",
    [({"publish_errors": True}, True), ({"publish_errors": False}, False), ({}, False)],
)
def test_extra_errors(
    reporter_config, errors_reported, mock_phabricator, mock_try_task
):
    """
    Test Phabricator reporter publication with some errors outside of patch
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision
    from code_review_bot.tasks.lint import MozLintIssue

    def _check_inline(request):
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])

        assert details == {
            "__conduit__": {"token": "deadbeef"},
            "content": "Warning: Some not so bad python mistake [flake8: EYYY]",
            "diffID": 42,
            "filePath": "path/to/file.py",
            "isNewFile": 1,
            "lineLength": 0,
            "lineNumber": 2,
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": {"id": "PHID-XXXX-YYYYY"}}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "mozlint-warning"},
            json.dumps(resp),
        )

    def _check_comment(request):
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details == {
            "revision_id": 51,
            "message": VALID_MOZLINT_MESSAGE,
            "attach_inlines": 1,
            "__conduit__": {"token": "deadbeef"},
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "mozlint-comment"},
            json.dumps(resp),
        )

    def _check_message(request):
        payload = urllib.parse.parse_qs(request.body)
        assert payload["output"] == ["json"]
        assert len(payload["params"]) == 1
        details = json.loads(payload["params"][0])
        assert details == {
            "buildTargetPHID": "PHID-HMBT-test",
            "lint": [
                {
                    "char": 12,
                    "code": "EXXX",
                    "description": "Some bad python typo",
                    "line": 10,
                    "name": "source-test-mozlint-dummy",
                    "path": "path/to/file.py",
                    "severity": "error",
                }
            ],
            "unit": [],
            "type": "work",
            "__conduit__": {"token": "deadbeef"},
        }

        # Outputs dummy empty response
        resp = {"error_code": None, "result": None}
        return (
            201,
            {"Content-Type": "application/json", "unittest": "mozlint-error"},
            json.dumps(resp),
        )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createinline",
        callback=_check_inline,
    )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/harbormaster.sendmessage",
        callback=_check_message,
    )

    responses.add_callback(
        responses.POST,
        "http://phabricator.test/api/differential.createcomment",
        callback=_check_comment,
    )

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {"path/to/file.py": [1, 2, 3]}
        revision.files = ["path/to/file.py"]
        reporter = PhabricatorReporter(reporter_config, api=api)

    all_issues = [
        # Warning in patch
        MozLintIssue(
            analyzer="source-test-mozlint-dummy",
            path="path/to/file.py",
            column=25,
            level=Level.Warning,
            lineno=2,
            linter="flake8",
            message="Some not so bad python mistake",
            check="EYYY",
            revision=revision,
        ),
        # Error outside of patch
        MozLintIssue(
            analyzer="source-test-mozlint-dummy",
            path="path/to/file.py",
            column=12,
            level=Level.Error,
            lineno=10,
            linter="flake8",
            message="Some bad python typo",
            check="EXXX",
            revision=revision,
        ),
        # Warning outside of patch
        MozLintIssue(
            analyzer="source-test-mozlint-dummy",
            path="path/to/file.py",
            column=1,
            level=Level.Warning,
            lineno=25,
            linter="flake8",
            message="Random mistake that will be ignored",
            check="EZZZ",
            revision=revision,
        ),
    ]

    published_issues, patches = reporter.publish(all_issues, revision, [])
    assert len(published_issues) == 2 if errors_reported else 1
    assert len(patches) == 0

    # Check the callbacks have been used to publish:
    # - an inline comment for the warning in patch
    # - a top comment to summarize issues
    # - a lint result for the error outside of patch (when errors are set to be reported)
    assert len(responses.calls) > 0
    urls = [
        "http://phabricator.test/api/differential.createinline",
        "http://phabricator.test/api/differential.createcomment",
    ]
    markers = ["mozlint-warning", "mozlint-comment"]
    if errors_reported:
        urls.append("http://phabricator.test/api/harbormaster.sendmessage")
        markers.append("mozlint-error")

    assert [r.request.url for r in responses.calls[-len(urls) :]] == urls
    assert [
        r.response.headers.get("unittest") for r in responses.calls[-len(urls) :]
    ] == markers
