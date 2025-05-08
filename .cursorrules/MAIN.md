Below is a detailed prompt for Cursor.ai to generate a Python script that meets your requirements for performing SCIM provisioning within Azure. The script will iterate through groups attached to an enterprise application, force provisioning for all users in those groups, use OIDC for authentication, and be executable via GitHub Actions. The prompt incorporates the provided image attachment description and ensures the script is high-quality with tests.


# Prompt for Cursor.ai: Python Script for SCIM Provisioning in Azure

I need a high-quality Python script that performs SCIM provisioning tasks within Azure for a specific enterprise application. The script must be designed to run in a GitHub Actions workflow and use OIDC for authentication with Azure. Below are the detailed requirements and context for the script.

## Context

- I have an enterprise application in Azure named "AWS" with the app ID `38b38689-7b69-4908-beba-096f310b8090`.
- this enterprise app Id will be passed in as an enviroment variable to the build
- This application has several groups and users assigned to it, as detailed in the image attachment description below.
- The goal is to force SCIM provisioning for all users in the groups attached to this enterprise application by triggering the provisioning job for the application.

## Image Attachment Description

The image is a screenshot of the Microsoft Azure portal, specifically the "Users and groups" section of an enterprise application named "AWS" under the "Enterprise applications | All applications" menu. The URL in the browser indicates the page is hosted at `portal.azure.com`, managing user and group assignments for the application with the object ID `d45810fad-9021-4d6e-bf99-2ce9c50b4cdf` and app ID `38b38689-7b69-4908-beba-096f310b8090`. The interface displays a section titled "Users and groups" with a table listing assignments, including:

- **AP_AWS50_GlobalAdmins** (Group, User)
- **AP_AWS50_PE** (Group, User)
- **AP_AWS50_PE_Elevated** (Group, User)
- **AP_AWS50_ReadOnlyAccess** (Group, User)


Each entry has the "Role assigned" as "User." The page includes navigation options like "Overview," "Properties," "Users and groups," "Provisioning," and action buttons such as "Add user/group," "Edit assignment," and "Remove assignment."

## Requirements

### 1. Authentication
- Use the `azure-identity` library with `DefaultAzureCredential` to authenticate with Azure using OIDC.
- Assume the GitHub Actions workflow has set up the necessary environment variables (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, etc.) via the `azure/login` action.

### 2. Script Functionality
- Use the Microsoft Graph SDK for Python to interact with the Microsoft Graph API.
- **Steps:**
  1. Retrieve the service principal for the enterprise application using the app ID `38b38689-7b69-4908-beba-096f310b8090`.
  2. Get the synchronization jobs for the service principal.
  3. Select the appropriate synchronization job (e.g., the first active job or one identified as the SCIM provisioning job) and trigger it using the `start` action to force provisioning for all assigned users and groups.
- **Optional Functionality:**
  - Include commented-out code or a separate function to:
    - Retrieve groups assigned to the application via the `/servicePrincipals/{servicePrincipalId}/appRoleAssignments` endpoint, filtering for `principalType` as 'Group'.
    - Get users in each group via the `/groups/{groupId}/members` endpoint.
    - Trigger `provisionOnDemand` for each user using the `/servicePrincipals/{servicePrincipalId}/synchronization/jobs/{jobId}/provisionOnDemand` endpoint.
  - This is not required for the primary functionality but can be included for flexibility.

### 3. Error Handling and Logging
- Implement robust error handling for API calls (e.g., authentication failures, resource not found, rate limiting).
- Use Python's `logging` module to log key actions (e.g., starting the job, retrieving resources) and errors.

### 4. Testing
- Write unit tests using `pytest` to verify the script's functionality.
- Use `unittest.mock` to simulate Microsoft Graph API calls, testing:
  - Authentication with `DefaultAzureCredential`.
  - Retrieval of the service principal.
  - Retrieval and selection of synchronization jobs.
  - Triggering the provisioning job.
- Ensure tests are comprehensive and mock realistic API responses.

### 5. Documentation
- Include detailed comments in the code explaining each function and step.
- Provide a `README.md` snippet or inline documentation on:
  - Setting up the GitHub Actions workflow with OIDC authentication.
  - Required Azure AD application permissions (e.g., `Application.Read.All`, `Synchronization.ReadWrite.All`).

## Additional Notes
- The Azure AD application used for OIDC must have permissions like `Application.Read.All` and `Synchronization.ReadWrite.All`.
- Structure the script for maintainability (e.g., separate functions for API calls, error handling).
- The script should assume the provisioning job processes all assigned users and groups when triggered.

## Expected Outcome
- A Python script that:
  - Runs in a GitHub Actions workflow.
  - Authenticates with Azure via OIDC.
  - Triggers the SCIM provisioning job for the enterprise application with app ID `38b38689-7b69-4908-beba-096f310b8090`.
- The script must be high-quality, well-tested, and include documentation for setup and usage.

Please generate the script based on these specifications, ensuring all requirements are met.
