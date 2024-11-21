
---

> [!IMPORTANT]
> The recommended install method is `pip install shuku`. Pre-compiled binaries take longer to boot and require manual approval:
>
> - macOS: Right-click → Open.
> - Windows: More info → Run anyway.
> - Linux: `chmod +x shuku`

> [!TIP]
> ### Verifying build provenance
>
> These binaries include Sigstore attestations that prove they were built by the GitHub Actions workflow. To verify:
>
> 1. Install the GitHub CLI: https://cli.github.com
> 2. Run:
>    ```bash
>    gh attestation verify <downloaded-file> --repo welpo/shuku
>    ```
