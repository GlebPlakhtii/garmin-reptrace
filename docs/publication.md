# Preparing a public repository

Garmin RepTrace has an independent package, install path and README. The source retains
its AGPL-3.0-only license and upstream BSD attribution. Publication itself is a separate step:
these preparation tools do not create a GitHub repository, commit or push.

## Export a clean source tree

```bash
uv run python scripts/prepare_publication.py /tmp/garmin-reptrace-public
```

The destination must not exist. This copies an explicit allowlist of source,
tests, documentation, and package/build configuration.
It excludes `.git`, filled environment files, tokens, local review notes, private
training logs, backups, SQLite files, build artifacts and private import profiles.
It does not carry the old repository's history into a new standalone project.

Inspect the resulting tree and files before initializing a new repository. An
allowlist reduces accidental inclusion; it is not proof that every allowed source
file or old Git history is free of secrets. Review changes and any future added
fixtures or screenshots with the same care.

## Before publishing

- Run the checks and build from the exported checkout, not only the working tree.
- Verify screenshots show synthetic records and every local README link resolves.
- Keep `LICENSE`, `LICENSES/` and `NOTICE.md`; an independent identity does not erase provenance.
- Review GitHub issue templates and the manual container-publication workflow.
- Choose the GitHub owner/repository and visibility. No live repository URL is
  invented in the README; use GitHub's clone URL once the repository exists.
- Do not copy private `.data/manual-import-review.json` into the new repository.
- If importing old Git history instead, audit that history separately.

The Check workflow tests pushes and pull requests. Container publication is an
explicit **Publish container** workflow dispatch to the current repository's GHCR
namespace. No upstream Docker Hub credentials or upstream-maintainer assignment
is required.

## Source availability for network deployments

If you modify the application and operate it for remote users, provide a prominent
source-code offer that gives those users the Corresponding Source for the exact
running version, at no charge. A source repository or downloadable archive must
include the covered modifications and required build/install scripts. An unrelated
upstream link is not sufficient for a modified deployment. Keep credentials and
private records out of that source. See section 13 of the root AGPL license.
