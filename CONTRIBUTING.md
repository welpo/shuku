# Contributing to shuku

Hi!

Thanks for contributing to [shuku](https://github.com/welpo/shuku). Before implementing new features and changes, please [submit an issue](https://github.com/welpo/shuku/issues/new) so that we can discuss it.

We welcome contributions in many forms, including:

- Bug reports
- Feature requests
- Code patches
- Documentation improvements
- UI/UX suggestions

If you're not sure how to contribute or need help with something, please don't hesitate to reach out via the [issue tracker](https://github.com/welpo/shuku/issues), [discussions](https://github.com/welpo/shuku/discussions), or [email](mailto:osc@osc.garden?subject=[GitHub]%20shuku).

## Development setup

To set up your development environment:

1. [Install Poetry](https://python-poetry.org/docs/#installation):

   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Clone the repository and navigate to the project directory:

   ```bash
   git clone https://github.com/welpo/shuku.git
   cd shuku
   ```

3. Install the project dependencies:

   ```bash
   poetry install
   ```

4. Activate the virtual environment:

   ```bash
   poetry shell
   ```

Now you can run `shuku` within the shell:

```bash
shuku --help
```

The `shuku` command will be available within the `poetry shell` and is linked to the project's source code. Code changes will be immediately reflected.

## Useful commands

### Running tests

```bash
poetry run pytest
```

### Checking code coverage

```bash
poetry run pytest --cov=shuku
```

### Checking types

```bash
poetry run mypy shuku
```

## Pull requests

Working on your first pull request? You can learn how from this free video series:

[**How to Contribute to an Open Source Project on GitHub**](https://egghead.io/courses/how-to-contribute-to-an-open-source-project-on-github)

Please make sure the following is done when submitting a pull request:

1. **Keep your PR small**. Small pull requests are much easier to review and more likely to get merged. Make sure the PR does only one thing, otherwise please split it.
2. **Use descriptive titles**. It is recommended to follow this [commit message style](#conventional-commit-messages-with-gitmoji).
3. **Test your changes**. Make sure to test different configurations that might affect your changes.
4. **Update the documentation**. Make the necessary changes to README.md.
5. **Fill the PR template**. The template will guide you through the process of submitting a PR.

Our integration systems run automated tests to guard against mistakes. To speed things up, make sure you have done the following before submitting your PR:

- Make sure all new and existing tests pass with `poetry run pytest`.
- Run `poetry run mypy shuku` to check for type errors.
- Run `poetry run black {file/dir}` to format your code.
- If necessary, update the documentation (i.e. `README.md`).

You might find the [hooks in `.githooks/`](https://github.com/welpo/doteki/tree/main/.githooks) useful. Read more on the [pre-commit githook section](#pre-commit-githook).

### Conventional commit messages with gitmoji

Format: `<gitmoji> <type>(<scope>): <description>`

`<gitmoji>` is an emoji from the [gitmoji](https://gitmoji.dev/) list. It makes it easier to visually scan the commit history and quickly grasp the purpose of changes.

`<scope>` is optional. If your change affects a specific part of the codebase, consider adding the scope. Scopes should be brief but recognizable, e.g. `config`, `metadata`, or `logging`.

The various types of commits:

- `feat`: a new API or behaviour **for the end user**.
- `fix`: a bug fix **for the end user**.
- `style`: changes to the visual appearance.
- `docs`: a documentation change.
- `refactor`: a change to code that doesn't change behaviour, e.g. splitting files, renaming internal variables, improving code style…
- `test`: adding missing tests, refactoring tests…
- `chore`: upgrading dependencies, releasing new versions… Chores that are **regularly done** for maintenance purposes.
- `misc`: anything else that doesn't change production code, yet is not `test` nor `chore`. e.g. updating GitHub actions workflow.

The commits within your PR don't need to follow this convention (we'll [squash them](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/configuring-commit-squashing-for-pull-requests)). However, the PR title should be in this format. If you're not sure about the title, don't worry, we'll help you fix it. Your code is more important than conventions!

Example:

```text
✨ feat(metadata): extract title from filename
^  ^--^^--------^  ^-------------------------^
|  |   |           |
|  |   |           +-> Description in imperative and lowercase.
|  |   |
|  |   +-> The scope of the change.
|  |
|  +-------> Type: see above for the list we use.
|
+----------> A valid gitmoji.
```

## Coding guidelines

- Use [`black`](https://github.com/psf/black) to format your code before submitting a pull request.
- Functions should be type annotated. Use `mypy` to check for type errors.
- Keep the code clean and maintainable. Here are some guidelines:

<details>
  <summary>Click to expand guidelines</summary>

1. **Test coverage**: Ensure comprehensive code coverage and keep tests readable. 80% coverage is the minimum; 100% is nice to have.

2. **Short, focused functions**: Keep functions brief and adhere to a single responsibility. Minimise arguments and make function signatures intuitive.

3. **Descriptive naming**: Use unambiguous names to clarify function and variable purpose.

4. **Consistent level**: Maintain one level of abstraction or focus within functions.

5. **DRY**: Don't Repeat Yourself; abstract repeated code into functions.

6. **Error handling**: Use logging and provide clear, actionable error messages.

7. **Minimal comments**: Keep code self-explanatory. Explain the why, not the how.

8. **Early returns**: Avoid deep nesting.

</details>

## Pre-commit githook

### Introduction

We use a pre-commit githook to maintain code and file quality. [This script](https://github.com/welpo/shuku/blob/main/.githooks/pre-commit) performs a series of checks before allowing a commit.

### Setting up

To use the pre-commit githook, run the following command from the root of the repository. This configures the git hooks path and makes the script executable:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

## Code of conduct

We expect all contributors to follow our [Code of Conduct](./CODE_OF_CONDUCT.md). Please be respectful and professional when interacting with other contributors.

## License

The code is available under the [MIT license](./LICENSE).

Thank you for your contributions!
