# Scripted answers: csv-report

- Sort order of the groups? Ascending by the group value, compared as text.
- Number format of the totals? As the input is written when whole, otherwise two decimal places.
- Are blank lines in the file rows? No, they are skipped.
- What if the group column is empty in a row? The group is the empty text and is listed first.
- Which stream carries the report and which the errors? The report goes to stdout, every error to stderr.
- Exit status for a refused file? 1; for a bad command line, 2.
