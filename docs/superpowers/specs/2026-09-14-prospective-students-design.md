# Prospective students

Approved scope: show Yes in a new homepage column only when the professor's
webpage explicitly invites prospective students to apply or contact them to join.
Otherwise leave the cell empty; do not display No or unknown states.

Store the supporting quote and source URL. Their presence represents the positive
indication; no separate recruitment-state enum is needed. Show the evidence on
the detail page. Extract these fields with the existing research finalizer and
validate the quote against an identity-matched, cited extracted page. Do not infer
an invitation from student lists, contact details, general admissions information,
or expired recruitment notices. Existing records default to empty; regular checks
populate the fields through the existing update-review flow.

Implementation: add a nullable two-column SQLite migration, propagate evidence
through research, persistence, API and update snapshots, and render Yes or blank.
Verify evidence rejection, migration and persistence, proposal flow, UI rendering,
and production build without live provider calls.
