# Changelog

Welcome to the changelog for shuku. Here you will find a comprehensive list of all changes made to the project, chronologically sorted by release version.

We use [Semantic Versioning](https://semver.org/), formatted as MAJOR.MINOR.PATCH. Major version changes involve significant (breaking) changes, minor versions introduce features and improvements in a backward compatible manner, and patch versions are for bug fixes and minor tweaks.

## [0.0.7](https://github.com/welpo/shuku/compare/v0.0.6..v0.0.7) - 2026-01-04

### ✨ Features

- Support cover art in condensed audio ([#106](https://github.com/welpo/shuku/issues/106)) by @welpo

### 🐛 Bug fixes

- Gracefully handle KeyboardInterrupt ([0802d9f](https://github.com/welpo/shuku/commit/0802d9f206b9317208a07a0e33f157060cff22f5)) by @welpo

### 📝 Documentation

- Replace Black with Ruff ([20dbe6f](https://github.com/welpo/shuku/commit/20dbe6fbf2e9be125cc8e86aaeaeb0be5d5e9d0a)) by @welpo

### 🔧 Miscellaneous tasks

- Improve error for unsupported subtitle formats ([4aa9b80](https://github.com/welpo/shuku/commit/4aa9b8021139118cd8790bc3cafdcdd1f0dbf011)) by @welpo

## [0.0.6](https://github.com/welpo/shuku/compare/v0.0.5..v0.0.6) - 2025-08-23

### 🐛 Bug fixes

- Correct season/episode metadata extraction ([0bb6022](https://github.com/welpo/shuku/commit/0bb602217577c43a914d22d6c008b1b42923bf39)) by @welpo

### ♻️ Refactor

- Improve keyboard interruption handling ([f5de092](https://github.com/welpo/shuku/commit/f5de092bac9c0e2a1c34f7f9bb430792bad9438f)) by @welpo

## [0.0.5](https://github.com/welpo/shuku/compare/v0.0.4..v0.0.5) - 2025-03-23

### 🐛 Bug fixes

- *(windows)* Stop excluding _overlapped module ([c493239](https://github.com/welpo/shuku/commit/c49323903c5478375b56260c858f8bcbb7505d1b)) by @welpo

### 📝 Documentation

- Update installation instructions to include uv ([7ba081b](https://github.com/welpo/shuku/commit/7ba081b41ae7a6869f648fd90a63cb82010d52c7)) by @welpo

### 🔧 Miscellaneous tasks

- *(CI)* Add concurrency control to sumi action ([94ec268](https://github.com/welpo/shuku/commit/94ec2688df674967616235d004f4dcc626bd355d)) by @welpo
- *(README)* Add condensed vs original clip ([641c49d](https://github.com/welpo/shuku/commit/641c49dbf354e3c33bbefc18d4f02556c198df15)) by @welpo

## [0.0.4](https://github.com/welpo/shuku/compare/v0.0.3..v0.0.4) - 2024-12-27

### ✨ Features

- Handle KeyboardInterrupt gracefully ([2ad3af4](https://github.com/welpo/shuku/commit/2ad3af4a277b417d6a62cf353ed5c0db42418be6)) by @welpo

### 📝 Documentation

- Add isitmaintained.com badges to comparison ([15e9b44](https://github.com/welpo/shuku/commit/15e9b445dace318d11084a8e797eda615df4dab8)) by @welpo

### ♻️ Refactor

- *(help)* Ensure program name is "shuku" ([6fa632b](https://github.com/welpo/shuku/commit/6fa632bf860021ae905fc88df8bc1d09a6dcffe5)) by @welpo

### 🔧 Miscellaneous tasks

- *(CD)* Use PyInstaller instead of Nuitka ([cf7fcbf](https://github.com/welpo/shuku/commit/cf7fcbf141765148cd1b93230333c24e36d1987b)) by @welpo
- *(CD)* Set timeouts for release jobs ([3812d1e](https://github.com/welpo/shuku/commit/3812d1e066604438828c5922efa032601d4a5746)) by @welpo
- *(README)* Link development blog post ([cd2f346](https://github.com/welpo/shuku/commit/cd2f3467459f54a94265f960e7760983fddf770b)) by @welpo

## [0.0.3](https://github.com/welpo/shuku/compare/v0.0.2..v0.0.3) - 2024-11-26

### ✨ Features

- Improve skipped chapter logging ([0ff6af6](https://github.com/welpo/shuku/commit/0ff6af66b7a44243b25e77293b0f4283ed1b3130)) by @welpo

### 📝 Documentation

- Remove installation warning from release notice ([07bac0e](https://github.com/welpo/shuku/commit/07bac0e030f1fa659895ef7baad9ccf16b5423ba)) by @welpo
- Join repository metrics w/ main comparison table ([4648a9d](https://github.com/welpo/shuku/commit/4648a9daba15ad9420b14014e873a6661f130c48)) by @welpo

### ♻️ Refactor

- Reduce subtitle search verbosity ([8da5423](https://github.com/welpo/shuku/commit/8da5423967d256e3aab9f0992a5d484cf30e0a03)) by @welpo

### 🔧 Miscellaneous tasks

- *(CI)* Lint with Ruff ([0b32d88](https://github.com/welpo/shuku/commit/0b32d88673b7c7d0fceac6de955c72f6e9c99235)) by @welpo
- *(README)* Update condensation animation ([f7d1520](https://github.com/welpo/shuku/commit/f7d1520d02358991f89bc178536ad83f7c90bc79)) by @welpo

### 👥 New contributors

🫶 @renovate[bot] made their first contribution in [#6](https://github.com/welpo/shuku/pull/6)

## 0.0.2 - 2024-11-22

### ✨ Features

- Initial release ([0153329](https://github.com/welpo/shuku/commit/01533294eb6bae548112c8a16b5b025c2ae134ea)) by @welpo

### 🐛 Bug fixes

- *(config)* Dump default config in UTF-8 ([8f6647b](https://github.com/welpo/shuku/commit/8f6647bdc205dc11fb3145b8b67528b873631eb5)) by @welpo

### 📝 Documentation

- *(CONTRIBUTING)* Include dev in poetry install command ([00987ce](https://github.com/welpo/shuku/commit/00987ce9d9fe927e6de8fb38af3fba0de00c485b)) by @welpo
- *(README)* Add Python version(s) badge ([d19b53e](https://github.com/welpo/shuku/commit/d19b53e66097d9b50d84d69b493b2229ad8fcadd)) by @welpo
- *(README)* Add badges for CI & CD ([ca3f76c](https://github.com/welpo/shuku/commit/ca3f76c85d68e59b70a576b1f71b6cc7a2136aea)) by @welpo
- *(README)* Compare similar projects with badges ([7558e91](https://github.com/welpo/shuku/commit/7558e9135da4e5814f8d0a17b020b33f4218dd64)) by @welpo
- *(README)* Improve installation instructions ([14e6bc1](https://github.com/welpo/shuku/commit/14e6bc15bf8559b5c720fd52bbae29a536a00873)) by @welpo
- *(release)* Update notice to link GitHub Actions workflow ([d909bb2](https://github.com/welpo/shuku/commit/d909bb2991d22d1e590872fdfbd661c9e3483fd3)) by @welpo
- *(release)* Recommend `pipx` and link attestations ([b333c4b](https://github.com/welpo/shuku/commit/b333c4bd741e30329c91be4e66d71d04d6f8b628)) by @welpo

### ♻️ Refactor

- *(config)* Use `choices` for `if_file_exists` ([95368e7](https://github.com/welpo/shuku/commit/95368e720c1c868a85e0c16ed03eacea5ea192e1)) by @welpo

### ✅ Testing

- Ignore version metadata when comparing LRC files ([0306775](https://github.com/welpo/shuku/commit/03067752b2bd6a26a6c52087a2b796f9fd5bd452)) by @welpo

### 🔧 Miscellaneous tasks

- *(CD)* Build wheels once ([2ed4d03](https://github.com/welpo/shuku/commit/2ed4d03d269548fd0be64f1b9fab015e9bbb9d1e)) by @welpo
- *(CD)* Install only main and build ([169f08c](https://github.com/welpo/shuku/commit/169f08c0fbcac3cf27f0e82b54a9936f96d42144)) by @welpo
- *(CD)* Stop trying to upload binaries to PyPI ([b08a6c5](https://github.com/welpo/shuku/commit/b08a6c52ca22bf55209e2b9e8bd921e87c243542)) by @welpo
- *(CD)* Pypi trusted publishing & publish all wheels ([83942f0](https://github.com/welpo/shuku/commit/83942f0ae9f382920a3e012c453dd71f335148ca)) by @welpo
- *(CD)* Create attestation for packaged executables ([cf4caf2](https://github.com/welpo/shuku/commit/cf4caf22253052a3b44a862cb045516ef466a42e)) by @welpo
- *(git-cliff)* Ignore pre-releases ([6223d99](https://github.com/welpo/shuku/commit/6223d99b2d869150cfaac878cf358185febf16a5)) by @welpo
- *(release)* Automate version upgrades ([eeb3075](https://github.com/welpo/shuku/commit/eeb3075452015c43594d016560a6e0782560716c)) by @welpo
- Rename ci.yaml to ci.yml ([5fa1179](https://github.com/welpo/shuku/commit/5fa117940c55c572fd60aa6ee59d27ff0dfd7960)) by @welpo

### 👥 New contributors

🫶 @welpo made their first contribution

<!-- generated by git-cliff -->
