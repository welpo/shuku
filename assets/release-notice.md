
---

> [!TIP]
> ### Verifying build provenance
>
> These binaries include Sigstore [attestations](https://github.com/welpo/shuku/attestations) that prove they were built by the [GitHub Actions workflow](https://github.com/welpo/shuku/blob/main/.github/workflows/cd.yml). To verify:
>
> 1. Install the GitHub CLI: https://cli.github.com
> 2. Run:
>    ```bash
>    gh attestation verify <downloaded-file> --repo welpo/shuku
>    ```
