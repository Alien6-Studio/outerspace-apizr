## API Endpoints <!-- markdownlint-disable MD041 -->

Fast Apizr provides the following API endpoints:

### POST /get_fastapi_code

#### Parameters

- `configuration` (string, optional): The Python version to use for the analysis. Defaults to "3.8".
- `file` (bytes, required): The file to analyze.

#### Returns

A dictionary with the analysis result.
