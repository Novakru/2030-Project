# ChemputerXDL

Bindings for the Chemputer platform to XDL.

## Development

Here are a few guidelines for contributing to ChemputerXDL.

### Issues

- All changes to the code should be tracked through GitLab issues.
- Issues can be anything from a declaration of a simple enhancement or bug fix you plan to do, to an open-ended question that requires lengthy discussion.
- Issues should be labelled appropriately.

#### Issue Labels

- **Priority - Low** — May not need done at all but worth discussing.
- **Priority - Medium** — Definitely should be implemented, but not urgent. Workaround available.
- **Priority - High** — Should be implemented as soon as possible. Breaking and no workaround available.
- **Type - Bug** — Something not working as intended.
- **Type - Enhancement** — Suggestion of a new feature, or modification of existing behaviour.
- **Type - Maintenance** — Suggestion of something that should be done but does not affect the behaviour of the code in any way, e.g. add documentation, refactor, add tests, etc.
- **Ready-to-implement** — Discussion is either not needed or has reached a consensus and the change can be implemented.

### Starting work on an issue

- Do not begin work on an issue until a rigorous definition of what will be implemented has been written and agreed upon. For simple issues, this may just involve you. For more complex issues, this could involve consensus from multiple people. Issues at this stage should be labelled as "Ready-to-implement".
- If you're not completely sure what an issue requires, ask!
- Assign yourself to the issue when you start working on it.
- Do not start work on an issue to which someone else is already assigned. If you believe the assignee isn't actually working on the issue, feel free to ask them and then assign yourself.

### Branching

- Unless there is very good reason, always branch off `master`.
- Use a branch name that includes your initials, the issue number, and a short title for the issue, e.g. `MC/#145-add-zero-volumes`.
- When you make the branch, please immediately delete `.gitlab-ci.yml`. This means you don't run pointless CI pipelines when pushing to the branch.

### Submitting an MR

1. Make sure linting using `flake8 .` does not throw any errors, and you have not left any print statements.
2. Make sure all tests pass using `pytest tests -m "unit or integration" -rf`
3. Add `.gitlab-ci.yml` back using `git checkout master -- .gitlab-ci.yml`
4. Create a merge request (MR) from your branch to `master` with a short title describing the issue and a clear description of what has been implemented.
5. Check the "Changes" tab to make sure you are happy with all the changes contained in the MR.
6. Tell someone with merging permissions that the MR is ready.

### Merging an MR

1. Rebase against master if there are merge conflicts using `git rebase -i master`
2. Check for any obvious coding errors including but not limited to over-complicatedness, lack of documentation, or style errors.
3. If appropriate, check that a unit test has been added to verify that the changes actually achieve the behaviour they claim to.
4. If appropriate, verify that physical testing of the changes has been carried out.
5. Merge, make sure the merge request is mentioned in the issue, and close the issue. Depending on the wording of the merge request description this may happen automatically.
