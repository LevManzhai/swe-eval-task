# platformdirs: XDG directories wrong in unusual environments

The repository in `/workspace/repo` is
[platformdirs](https://github.com/tox-dev/platformdirs), the library that pip,
virtualenv, black and many other tools use to decide where to put their data,
config, cache and runtime files.

## What a user reported

> Our service runs as root under `sudo` with `use_site_for_root=True`. Config and
> data go to the system directories as documented, but
> `user_documents_path(use_site_for_root=True)` is a `TypeError`, and
> `PlatformDirs(use_site_for_root=True).user_documents_dir` still returns the
> invoking user's `~/Documents` that `sudo` passed on through `XDG_DOCUMENTS_DIR`.
> With `ensure_exists=True` we end up creating directories in their home.

## What we want

Fix that, and treat it as one example of a wider problem: on Unix, platformdirs
gets rare but legitimate environments wrong in ways that don't match the
[XDG Base Directory Specification](https://specifications.freedesktop.org/basedir/latest/),
the `xdg-user-dirs` format, or platformdirs' own documented guarantees. We want
the following to hold:

1. **Environment values are read as the specification says.** An XDG variable
   is used only if it holds an absolute path, and an accepted value is used
   exactly as given: whitespace is part of a path, not padding around it. The
   same goes for every entry of a `*_DIRS` list. `HOME` is used only when it
   is an absolute path; otherwise platformdirs behaves as if it were unset.
2. **Lists of directories are well formed.** A list of directories (the
   `*_dirs` properties, the iterators and `multipath=True`) names each
   directory once, however its entries happen to be spelled, and
   `multipath=True` never returns a joined string that a caller would split
   into different directories than the ones meant.
3. **`user-dirs.dirs` is read safely.** A missing, unreadable or odd
   `user-dirs.dirs` never breaks a call: the defaults apply. Reading it takes
   time linear in its size, whatever it contains.
4. **The runtime directory is safe.** `user_runtime_dir` only returns a
   directory that the spec allows and that no other user can replace, through
   the directory itself or any directory above it, however the path is
   spelled. Its fallbacks are well-formed paths on every system.
5. **`use_site_for_root` means what it says.** For root with
   `use_site_for_root=True`, nothing inherited from the invoking user is used,
   in every API that has a `user_*` directory, module functions included, and
   nothing is created in their home.
6. **`ensure_exists` either gives you a directory or raises.** It never
   silently returns a path that is not a usable directory.
7. **The tooling stays usable.** `python -m platformdirs` reports what it can
   in any environment, and the isolation helpers in `platformdirs.testing`
   behave the same wherever the working directory is moved.

Behaviour that has nothing to do with these points must not change. If an
existing test in `tests/` pins down a behaviour, keep it.

## Notes

- The test suite passes as it is (`python -m pytest tests`). It doesn't cover
  these cases.
- Your changes are graded by hidden tests that use platformdirs' public API:
  the module functions, `PlatformDirs` and the platform classes (the Unix one
  in particular, with the environment, `os.geteuid` and the file system set up
  by the tests), `python -m platformdirs` and `platformdirs.testing`. The exact
  wording of warnings and error messages is not graded.
