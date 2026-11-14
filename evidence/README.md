# Verification evidence

`unit-tests.txt`: local Rocky 9 Python regression run.
`gui-smoke-el9.txt`: empty output with process exit 0 from GUI construction using
Xvfb on the builder; does not prove interactive behavior or real pool management.

Live test host read-only SSH probe on November 14, 2026 returned
`Permission denied (publickey,password)`. No host changes were made. Approved
access is needed for live qualification; packaging work can continue independently.
