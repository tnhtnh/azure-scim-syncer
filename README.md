# Azure SCIM Syncer

This Python script automates SCIM provisioning tasks within Azure for a specified enterprise application. It can be run in a GitHub Actions workflow and uses OpenID Connect (OIDC) for authentication with Azure.

## Features

- Authenticates with Azure using OIDC (`azure-identity` with `DefaultAzureCredential`).
- Uses the Microsoft Graph SDK for Python to interact with the Microsoft Graph API.
- Retrieves the service principal for a target enterprise application.
- Identifies and triggers the SCIM synchronization job for the application, forcing provisioning for all assigned users and groups.
- (Optional) Provides functionality to perform on-demand provisioning for individual users within specific groups assigned to the application.
- Includes robust error handling and logging.

## Prerequisites

- Python 3.10+
- An Azure Active Directory (Azure AD) tenant.
- An enterprise application in Azure AD configured for SCIM provisioning.
- An Azure AD application registration to be used for OIDC authentication by GitHub Actions.

## Setup

### 1. Azure AD Application Registration for OIDC

   a. **Register an Application**:
      - In the Azure portal, navigate to **Azure Active Directory** > **App registrations** > **New registration**.
      - Give it a meaningful name (e.g., `github-actions-scim-syncer`).
      - Supported account types: **Accounts in this organizational directory only ({Your Tenant Name} only)**.
      - Redirect URI: Leave blank for now.
      - Click **Register**.

   b. **API Permissions**:
      - Go to the registered application's **API permissions** page.
      - Click **Add a permission** > **Microsoft Graph** > **Application permissions**.
      - Add the following permissions:
        - `Application.Read.All` (to find the enterprise application's service principal)
        - `Synchronization.ReadWrite.All` (to read and start synchronization jobs)
        - `AppRoleAssignment.ReadWrite.All` (if using the optional on-demand group/user functions, to read app role assignments)
        - `GroupMember.Read.All` (if using the optional on-demand group/user functions, to read group members)
      - Click **Add permissions**.
      - Click **Grant admin consent for {Your Tenant Name}** for the added permissions.

   c. **Certificates & Secrets (Federated Credentials for OIDC)**:
      - Go to the registered application's **Certificates & secrets** page.
      - Select the **Federated credentials** tab.
      - Click **Add credential**.
      - **Federated credential scenario**: Select `GitHub Actions deploying Azure resources`.
      - **Organization**: Your GitHub organization name (e.g., `my-github-org`).
      - **Repository**: Your GitHub repository name (e.g., `azure-scim-syncer`).
      - **Entity type**: `Branch` (or `Pull request`, `Tag`, `Environment` depending on your workflow trigger).
      - **Branch name**: `main` (or the specific branch that will run the workflow).
      - **Name**: A descriptive name (e.g., `github-actions-main-branch`).
      - Click **Add**.

   d. **Collect IDs**:
      - From the application's **Overview** page, note down:
        - **Application (client) ID**
        - **Directory (tenant) ID**

### 2. GitHub Actions Workflow Setup

   a. **Repository Secrets**:
      - In your GitHub repository, go to **Settings** > **Secrets and variables** > **Actions**.
      - Add the following secrets:
        - `AZURE_CLIENT_ID`: The Application (client) ID of the Azure AD app registration (from step 1d).
        - `AZURE_TENANT_ID`: The Directory (tenant) ID (from step 1d).
        - `AZURE_SUBSCRIPTION_ID`: Your Azure Subscription ID (can be any valid subscription ID linked to the tenant, as `azure/login` requires it, though the script itself might not directly use it if only interacting with Azure AD via Graph).
        - `AZURE_APP_ID`: The **Application (client) ID** of the **Enterprise Application** you want to synchronize (e.g., `38b38689-7b69-4908-beba-096f310b8090` for the "AWS" app mentioned in the prompt).

   b. **GitHub Actions Workflow File**:
      - Create a workflow file (e.g., `.github/workflows/scim_sync.yml`) with the content provided in the [GitHub Actions Workflow](#github-actions-workflow) section below.

### 3. Local Development (Optional)

   a. **Install Dependencies**:
      ```bash
      python -m venv .venv
      source .venv/bin/activate  # On Windows: .venv\Scripts\activate
      pip install -r requirements.txt
      ```

   b. **Environment Variables**:
      - Create a `.env` file in the root of the project:
        ```env
        AZURE_CLIENT_ID="your-oidc-app-client-id"
        AZURE_TENANT_ID="your-azure-tenant-id"
        AZURE_APP_ID="your-enterprise-app-client-id-to-sync"
        # For local development, you might need AZURE_CLIENT_SECRET if not using a browser/CLI login method supported by DefaultAzureCredential
        # AZURE_CLIENT_SECRET="your-oidc-app-client-secret" 
        ```
      - **Note**: For local development, `DefaultAzureCredential` will attempt various authentication methods (Environment, Managed Identity, Azure CLI, etc.). Ensure one is configured or provide `AZURE_CLIENT_SECRET` if using client secret authentication locally (not recommended for GitHub Actions).

## Usage

### Running with GitHub Actions

The script is designed to be triggered by the GitHub Actions workflow (e.g., on a schedule or manual trigger). The workflow will handle authentication and execution.

### Running Locally

1. Ensure you have authenticated with Azure CLI (`az login`) or have the necessary environment variables set for `DefaultAzureCredential` (see `.env` file example).
2. Set the `AZURE_APP_ID` environment variable to the client ID of the enterprise application whose SCIM provisioning job you want to trigger.
3. Run the script:
   ```bash
   python src/scim_syncer.py
   ```

### Running On-Demand Provisioning (Optional)

To run the on-demand provisioning for all users in an application (experimental, requires careful testing and correct `ruleId` discovery/setting in the code):

Set the environment variable `RUN_ON_DEMAND_PROVISIONING` to `true`.

```bash
RUN_ON_DEMAND_PROVISIONING=true python src/scim_syncer.py
```

## Script Overview (`src/scim_syncer.py`)

- **`get_graph_client()`**: Initializes `GraphServiceClient` with `DefaultAzureCredential`.
- **`get_service_principal_id(graph_client, app_id)`**: Finds the service principal object ID for the given enterprise application client ID.
- **`get_synchronization_job_id(graph_client, service_principal_id)`**: Retrieves the ID of the SCIM synchronization job (assumes the first relevant job).
- **`start_synchronization_job(graph_client, service_principal_id, job_id)`**: Starts the specified synchronization job.
- **`main()`**: Orchestrates the above steps.
- **Optional Functions for On-Demand Provisioning**:
  - `get_assigned_groups(...)`: Retrieves groups assigned to the application.
  - `get_group_members(...)`: Retrieves members of a group.
  - `provision_user_on_demand(...)`: Triggers provisioning for a single user.
  - `provision_all_users_on_demand_in_app(...)`: Orchestrates on-demand provisioning for all users in assigned groups.

## GitHub Actions Workflow

Create `.github/workflows/scim_sync.yml`:

```yaml
name: Azure SCIM Sync

on:
  workflow_dispatch: # Allows manual triggering
  # schedule:
  #   - cron: '0 2 * * *' # Example: Run daily at 2 AM UTC

permissions:
  id-token: write # Required for OIDC
  contents: read # Required to checkout the repository

jobs:
  scim_sync:
    runs-on: ubuntu-latest
    environment: production # Optional: if you have environment-specific secrets
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11' # Or your desired Python version

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Azure Login
        uses: azure/login@v1
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }} # Required by azure/login, even if script only uses Graph
          enable-AzPSSession: false # Set to true if you also need Azure PowerShell

      - name: Run SCIM Syncer
        env:
          AZURE_APP_ID: ${{ secrets.AZURE_APP_ID }} # Enterprise App ID to sync
          # RUN_ON_DEMAND_PROVISIONING: 'false' # Set to 'true' to run on-demand sync
        run: python src/scim_syncer.py

      - name: Azure Logout
        if: always() # Ensure logout even if previous steps fail
        run: |
          az logout
          az cache purge
          az account clear
        continue-on-error: true
```

## Testing

Unit tests are located in the `tests/` directory and use `pytest`.

To run tests:

```bash
pip install pytest pytest-cov requests-mock
pytest
```

To generate a coverage report:

```bash
pytest --cov=src --cov-report=html
```
Open `htmlcov/index.html` in your browser to view the report.

## Security Considerations

- **Principle of Least Privilege**: The Azure AD application used for OIDC should only have the minimum required permissions (`Application.Read.All`, `Synchronization.ReadWrite.All`).
- **Secrets Management**: GitHub Actions secrets are used to store sensitive information like client IDs and tenant IDs. Do not hardcode these in the script.
- **Error Handling**: The script includes error handling for API calls and logs important actions and errors.
- **Regular Review**: Regularly review Azure AD application permissions and GitHub Actions workflow configurations.

## Troubleshooting

- **Authentication Issues**: 
  - Verify `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` are correct in GitHub secrets.
  - Ensure the Federated Credential in Azure AD app registration matches your GitHub repository and branch/environment.
  - Check Azure AD sign-in logs for the managed identity/service principal associated with the OIDC token for any errors.
- **Graph API Errors**: 
  - Check the script logs for detailed error messages from the Graph API.
  - Ensure the Azure AD app has the required API permissions and admin consent has been granted.
  - The target enterprise application (`AZURE_APP_ID`) must exist and be correctly configured for SCIM.
- **Job Not Starting**: 
  - Verify the `AZURE_APP_ID` points to the correct enterprise application.
  - Ensure a SCIM provisioning job is configured and enabled for that application in Azure AD. 