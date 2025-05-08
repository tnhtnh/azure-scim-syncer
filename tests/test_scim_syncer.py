import asyncio
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.identity.aio import DefaultAzureCredential # For async mocking
from msgraph import GraphServiceClient
from msgraph.generated.models.service_principal import ServicePrincipal
from msgraph.generated.models.synchronization_job import SynchronizationJob
from msgraph.generated.models.app_role_assignment import AppRoleAssignment
from msgraph.generated.models.user import User
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from msgraph.generated.models.o_data_errors.main_error import MainError

# Add src directory to sys.path to allow direct import of scim_syncer
import sys

# Construct the absolute path to the src directory
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(os.path.dirname(current_dir), "src")
sys.path.insert(0, src_path)

import scim_syncer # type: ignore

# Test constants
TEST_APP_ID = "38b38689-7b69-4908-beba-096f310b8090"
TEST_SP_ID = "test-sp-id"
TEST_JOB_ID = "test-job-id"
TEST_GROUP_ID_1 = "test-group-id-1"
TEST_USER_ID_1 = "test-user-id-1"

@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch):
    monkeypatch.setenv("AZURE_APP_ID", TEST_APP_ID)
    # Clear any existing handlers on the root logger to avoid duplicate logs in tests
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    # Configure logging for tests
    logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler(sys.stdout)])
    # Reload scim_syncer to pick up patched env var if it was loaded at module level
    import importlib
    importlib.reload(scim_syncer)

@pytest.fixture
def mock_graph_service_client():
    """Provides a mock GraphServiceClient with mocked fluent methods."""
    mock_client = AsyncMock(spec=GraphServiceClient)

    # Mock service_principals attribute
    mock_client.service_principals = MagicMock()

    # Mock service_principals.get method (async)
    mock_client.service_principals.get = AsyncMock()

    # Mock service_principals.by_service_principal_id method (sync, returns builder)
    mock_sp_item_builder = MagicMock(name="ServicePrincipalItemRequestBuilder")
    mock_client.service_principals.by_service_principal_id.return_value = mock_sp_item_builder

    # Mock attributes/methods on the ServicePrincipalItemRequestBuilder
    mock_sp_item_builder.synchronization = MagicMock(name="SynchronizationRequestBuilder")
    mock_sp_item_builder.synchronization.jobs = MagicMock(name="JobsRequestBuilder")
    mock_sp_item_builder.synchronization.jobs.get = AsyncMock() # async action

    mock_sync_job_item_builder = MagicMock(name="SynchronizationJobItemRequestBuilder")
    mock_sp_item_builder.synchronization.jobs.by_synchronization_job_id.return_value = mock_sync_job_item_builder

    mock_sync_job_item_builder.start = MagicMock(name="StartRequestBuilder")
    mock_sync_job_item_builder.start.post = AsyncMock() # async action

    mock_sync_job_item_builder.provision_on_demand = MagicMock(name="ProvisionOnDemandRequestBuilder")
    mock_sync_job_item_builder.provision_on_demand.post = AsyncMock() # async action

    mock_sp_item_builder.app_role_assigned_to = MagicMock(name="AppRoleAssignedToRequestBuilder")
    mock_sp_item_builder.app_role_assigned_to.get = AsyncMock() # async action

    # Mock groups attribute
    mock_client.groups = MagicMock()

    # Mock groups.by_group_id method (sync, returns builder)
    mock_group_item_builder = MagicMock(name="GroupItemRequestBuilder")
    mock_client.groups.by_group_id.return_value = mock_group_item_builder

    # Mock attributes/methods on the GroupItemRequestBuilder
    mock_group_item_builder.members = MagicMock(name="MembersRequestBuilder")
    mock_group_item_builder.members.get = AsyncMock() # async action

    return mock_client

@patch("scim_syncer.DefaultAzureCredential", spec=DefaultAzureCredential)
@patch("scim_syncer.GraphServiceClient", spec=GraphServiceClient)
@pytest.mark.asyncio
async def test_get_graph_client_success(MockGraphServiceClient, MockDefaultAzureCredential):
    """Tests successful GraphServiceClient initialization."""
    mock_credential_instance = MockDefaultAzureCredential.return_value
    mock_client_instance = MockGraphServiceClient.return_value

    client = await scim_syncer.get_graph_client()

    MockDefaultAzureCredential.assert_called_once()
    MockGraphServiceClient.assert_called_once_with(
        credentials=mock_credential_instance, scopes=["https://graph.microsoft.com/.default"]
    )
    assert client == mock_client_instance

@patch("scim_syncer.DefaultAzureCredential", side_effect=Exception("Auth error"))
@pytest.mark.asyncio
async def test_get_graph_client_failure(MockDefaultAzureCredential):
    """Tests GraphServiceClient initialization failure."""
    with pytest.raises(Exception, match="Auth error"):
        await scim_syncer.get_graph_client()
    MockDefaultAzureCredential.assert_called_once()

@pytest.mark.asyncio
async def test_get_service_principal_id_success(mock_graph_service_client):
    """Tests successful retrieval of service principal ID."""
    sp = ServicePrincipal(id=TEST_SP_ID, app_id=TEST_APP_ID)
    mock_response = MagicMock()
    mock_response.value = [sp]
    mock_graph_service_client.service_principals.get.return_value = mock_response

    sp_id = await scim_syncer.get_service_principal_id(mock_graph_service_client, TEST_APP_ID)

    mock_graph_service_client.service_principals.get.assert_called_once()
    call_args, call_kwargs = mock_graph_service_client.service_principals.get.call_args

    # The request_configuration is now an object, not a lambda
    assert "request_configuration" in call_kwargs
    passed_config_object = call_kwargs["request_configuration"]

    # Assert that the passed config object has the correct query parameters
    assert passed_config_object is not None
    assert passed_config_object.query_parameters is not None
    assert passed_config_object.query_parameters.filter == f"appId eq '{TEST_APP_ID}'"
    assert passed_config_object.query_parameters.select == ["id", "appId", "displayName"]

    assert sp_id == TEST_SP_ID

@pytest.mark.asyncio
async def test_get_service_principal_id_not_found(mock_graph_service_client):
    """Tests service principal not found."""
    mock_response = MagicMock()
    mock_response.value = []
    mock_graph_service_client.service_principals.get.return_value = mock_response

    sp_id = await scim_syncer.get_service_principal_id(mock_graph_service_client, TEST_APP_ID)
    assert sp_id is None

@pytest.mark.asyncio
async def test_get_service_principal_id_odata_error(mock_graph_service_client, caplog):
    """Tests ODataError during service principal retrieval."""
    error = ODataError(error=MainError(message="Test OData Error"))
    mock_graph_service_client.service_principals.get.side_effect = error

    with pytest.raises(ODataError):
        await scim_syncer.get_service_principal_id(mock_graph_service_client, TEST_APP_ID)
    assert f"OData error retrieving service principal for app ID {TEST_APP_ID}: Test OData Error" in caplog.text

@pytest.mark.asyncio
async def test_get_synchronization_job_id_success(mock_graph_service_client):
    """Tests successful retrieval of synchronization job ID."""
    job = SynchronizationJob(id=TEST_JOB_ID)
    mock_response = MagicMock()
    mock_response.value = [job]
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.synchronization.jobs.get.return_value = mock_response

    job_id = await scim_syncer.get_synchronization_job_id(mock_graph_service_client, TEST_SP_ID)

    mock_graph_service_client.service_principals.by_service_principal_id.assert_called_with(TEST_SP_ID)
    mock_sp_item.synchronization.jobs.get.assert_called_once()
    assert job_id == TEST_JOB_ID

@pytest.mark.asyncio
async def test_get_synchronization_job_id_not_found(mock_graph_service_client):
    """Tests synchronization job not found."""
    mock_response = MagicMock()
    mock_response.value = []
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.synchronization.jobs.get.return_value = mock_response

    job_id = await scim_syncer.get_synchronization_job_id(mock_graph_service_client, TEST_SP_ID)
    assert job_id is None

@pytest.mark.asyncio
async def test_get_synchronization_job_id_odata_error(mock_graph_service_client, caplog):
    """Tests ODataError during synchronization job retrieval."""
    error = ODataError(error=MainError(message="Job OData Error"))
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.synchronization.jobs.get.side_effect = error

    with pytest.raises(ODataError):
        await scim_syncer.get_synchronization_job_id(mock_graph_service_client, TEST_SP_ID)

@pytest.mark.asyncio
async def test_start_synchronization_job_success(mock_graph_service_client):
    """Tests successful start of synchronization job."""
    mock_job_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value.synchronization.jobs.by_synchronization_job_id.return_value
    mock_job_item.start.post.return_value = None # Simulating a successful void response

    await scim_syncer.start_synchronization_job(mock_graph_service_client, TEST_SP_ID, TEST_JOB_ID)

    mock_graph_service_client.service_principals.by_service_principal_id.assert_called_with(TEST_SP_ID)
    mock_graph_service_client.service_principals.by_service_principal_id.return_value.synchronization.jobs.by_synchronization_job_id.assert_called_with(TEST_JOB_ID)
    mock_job_item.start.post.assert_called_once()

@pytest.mark.asyncio
async def test_start_synchronization_job_odata_error(mock_graph_service_client, caplog):
    """Tests ODataError during starting synchronization job."""
    error = ODataError(error=MainError(message="Start Job OData Error"))
    mock_job_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value.synchronization.jobs.by_synchronization_job_id.return_value
    mock_job_item.start.post.side_effect = error

    with pytest.raises(ODataError):
        await scim_syncer.start_synchronization_job(mock_graph_service_client, TEST_SP_ID, TEST_JOB_ID)
    assert "OData error starting synchronization job: Start Job OData Error" in caplog.text

@patch("scim_syncer.get_graph_client")
@patch("scim_syncer.get_service_principal_id")
@patch("scim_syncer.get_synchronization_job_id")
@patch("scim_syncer.start_synchronization_job")
@pytest.mark.asyncio
async def test_main_success(
    mock_start_job, mock_get_job_id, mock_get_sp_id, mock_get_client, caplog
):
    """Tests the main function happy path."""
    mock_get_client.return_value = AsyncMock(spec=GraphServiceClient)
    mock_get_sp_id.return_value = TEST_SP_ID
    mock_get_job_id.return_value = TEST_JOB_ID
    mock_start_job.return_value = None

    await scim_syncer.main()

    mock_get_client.assert_called_once()
    mock_get_sp_id.assert_called_once_with(mock_get_client.return_value, TEST_APP_ID)
    mock_get_job_id.assert_called_once_with(mock_get_client.return_value, TEST_SP_ID)
    mock_start_job.assert_called_once_with(mock_get_client.return_value, TEST_SP_ID, TEST_JOB_ID)
    assert "SCIM provisioning process completed successfully." in caplog.text

@patch("scim_syncer.get_graph_client")
@patch("scim_syncer.get_service_principal_id", return_value=None) # SP not found
@pytest.mark.asyncio
async def test_main_sp_not_found(mock_get_sp_id, mock_get_client, caplog):
    """Tests main function when service principal is not found."""
    mock_get_client.return_value = AsyncMock(spec=GraphServiceClient)

    await scim_syncer.main()

    mock_get_sp_id.assert_called_once()
    assert f"Could not find service principal for app ID {TEST_APP_ID}. Exiting." in caplog.text

@patch("scim_syncer.get_graph_client")
@patch("scim_syncer.get_service_principal_id", return_value=TEST_SP_ID)
@patch("scim_syncer.get_synchronization_job_id", return_value=None) # Job not found
@pytest.mark.asyncio
async def test_main_job_not_found(mock_get_job_id, mock_get_sp_id, mock_get_client, caplog):
    """Tests main function when synchronization job is not found."""
    mock_get_client.return_value = AsyncMock(spec=GraphServiceClient)

    await scim_syncer.main()

    mock_get_job_id.assert_called_once()
    assert f"Could not find synchronization job for service principal ID {TEST_SP_ID}. Exiting." in caplog.text

@patch("scim_syncer.get_graph_client")
@patch("scim_syncer.get_service_principal_id", side_effect=Exception("SP Error"))
@pytest.mark.asyncio
async def test_main_general_exception(mock_get_sp_id, mock_get_client, caplog):
    """Tests main function with a general exception."""
    mock_get_client.return_value = AsyncMock(spec=GraphServiceClient)

    await scim_syncer.main()
    assert "An error occurred during the SCIM provisioning process: SP Error" in caplog.text

# --- Tests for Optional Functions ---

@pytest.mark.asyncio
async def test_get_assigned_groups_success(mock_graph_service_client):
    """Tests successful retrieval of assigned groups."""
    assignment1 = AppRoleAssignment(principal_id=TEST_GROUP_ID_1, principal_type="Group")
    # Set the principal_display_name attribute, which might be None if not present in the actual response
    assignment1.principal_display_name = "Test Group 1 Name"
    mock_response = MagicMock()
    mock_response.value = [assignment1]
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.app_role_assigned_to.get.return_value = mock_response

    groups_info = await scim_syncer.get_assigned_groups(mock_graph_service_client, TEST_SP_ID)
    expected_groups_info = [{"id": TEST_GROUP_ID_1, "displayName": "Test Group 1 Name"}]
    assert groups_info == expected_groups_info
    mock_sp_item.app_role_assigned_to.get.assert_called_once()
    call_args, call_kwargs = mock_sp_item.app_role_assigned_to.get.call_args
    
    assert "request_configuration" in call_kwargs
    request_config_lambda = call_kwargs["request_configuration"] 

    mock_req_config = MagicMock()
    mock_req_config.query_parameters = MagicMock()
    mock_req_config.query_parameters.filter = None
    mock_req_config.query_parameters.select = None

    request_config_lambda(mock_req_config)

    assert mock_req_config.query_parameters.filter == "principalType eq 'Group'"
    assert mock_req_config.query_parameters.select == ["principalId", "principalDisplayName"]

@pytest.mark.asyncio
async def test_get_assigned_groups_no_groups(mock_graph_service_client):
    """Tests retrieval when no groups are assigned."""
    mock_response = MagicMock()
    mock_response.value = []
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.app_role_assigned_to.get.return_value = mock_response

    group_ids = await scim_syncer.get_assigned_groups(mock_graph_service_client, TEST_SP_ID)
    assert group_ids == []

@pytest.mark.asyncio
async def test_get_group_members_success(mock_graph_service_client):
    """Tests successful retrieval of group members (users)."""
    user1 = User(id=TEST_USER_ID_1)
    # odata_type is usually @odata.type in actual responses, but the model property is odata_type
    user1.odata_type = "#microsoft.graph.user" # Important for filtering if done in code
    mock_response = MagicMock()
    mock_response.value = [user1]
    mock_group_item = mock_graph_service_client.groups.by_group_id.return_value
    mock_group_item.members.get.return_value = mock_response

    user_ids = await scim_syncer.get_group_members(mock_graph_service_client, TEST_GROUP_ID_1)
    assert user_ids == [TEST_USER_ID_1]
    mock_graph_service_client.groups.by_group_id.assert_called_with(TEST_GROUP_ID_1)
    mock_group_item.members.get.assert_called_once()

@pytest.mark.asyncio
async def test_provision_user_on_demand_success(mock_graph_service_client):
    """Tests successful triggering of provisionOnDemand."""
    mock_job_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value.synchronization.jobs.by_synchronization_job_id.return_value
    mock_job_item.provision_on_demand.post.return_value = None # Simulate success

    await scim_syncer.provision_user_on_demand(
        mock_graph_service_client, TEST_SP_ID, TEST_JOB_ID, TEST_USER_ID_1
    )

    mock_job_item.provision_on_demand.post.assert_called_once()
    args, kwargs = mock_job_item.provision_on_demand.post.call_args
    # Verify the body (subject) of the post request
    # The body is passed as a keyword argument 'body' to the post method
    assert kwargs['body'].object_id == TEST_USER_ID_1
    assert kwargs['body'].object_type_name == "User"

@patch("scim_syncer.get_service_principal_id", new_callable=AsyncMock)
@patch("scim_syncer.get_synchronization_job_id", new_callable=AsyncMock)
@patch("scim_syncer.get_assigned_groups", new_callable=AsyncMock)
@patch("scim_syncer.get_group_members", new_callable=AsyncMock)
@patch("scim_syncer.provision_user_on_demand", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_provision_all_users_on_demand_in_app_happy_path(
    mock_provision_user, mock_get_group_members, mock_get_assigned_groups, 
    mock_get_sync_job_id, mock_get_sp_id, mock_graph_service_client, caplog
):
    """Tests the orchestration for on-demand provisioning of all users."""
    mock_get_sp_id.return_value = TEST_SP_ID
    mock_get_sync_job_id.return_value = TEST_JOB_ID
    mock_get_assigned_groups.return_value = [{"id": TEST_GROUP_ID_1, "displayName": "Test Group 1"}]
    mock_get_group_members.return_value = [TEST_USER_ID_1]
    mock_provision_user.return_value = None

    await scim_syncer.provision_all_users_on_demand_in_app(mock_graph_service_client, TEST_APP_ID)

    mock_get_sp_id.assert_called_once_with(mock_graph_service_client, TEST_APP_ID)
    mock_get_sync_job_id.assert_called_once_with(mock_graph_service_client, TEST_SP_ID)
    mock_get_assigned_groups.assert_called_once_with(mock_graph_service_client, TEST_SP_ID)
    mock_get_group_members.assert_called_once_with(mock_graph_service_client, TEST_GROUP_ID_1)
    mock_provision_user.assert_called_once_with(
        mock_graph_service_client, TEST_SP_ID, TEST_JOB_ID, TEST_USER_ID_1
    )
    expected_log_message = f"Completed on-demand provisioning process for users in App ID: {TEST_APP_ID} (SP ID: {TEST_SP_ID})."
    assert expected_log_message in caplog.text

@patch("scim_syncer.get_service_principal_id", new_callable=AsyncMock, return_value=None)
@pytest.mark.asyncio
async def test_provision_all_users_on_demand_in_app_no_sp(mock_get_sp_id, mock_graph_service_client, caplog):
    await scim_syncer.provision_all_users_on_demand_in_app(mock_graph_service_client, TEST_APP_ID)
    assert f"Cannot perform on-demand provisioning: Service principal not found for app {TEST_APP_ID}." in caplog.text

@patch("scim_syncer.get_service_principal_id", new_callable=AsyncMock, return_value=TEST_SP_ID)
@patch("scim_syncer.get_synchronization_job_id", new_callable=AsyncMock, return_value=None)
@pytest.mark.asyncio
async def test_provision_all_users_on_demand_in_app_no_job(mock_get_sync_job_id, mock_get_sp_id, mock_graph_service_client, caplog):
    await scim_syncer.provision_all_users_on_demand_in_app(mock_graph_service_client, TEST_APP_ID)
    assert f"Cannot perform on-demand provisioning: Sync job not found for SP {TEST_SP_ID}." in caplog.text

@patch("scim_syncer.get_service_principal_id", new_callable=AsyncMock, return_value=TEST_SP_ID)
@patch("scim_syncer.get_synchronization_job_id", new_callable=AsyncMock, return_value=TEST_JOB_ID)
@patch("scim_syncer.get_assigned_groups", new_callable=AsyncMock, return_value=[])
@pytest.mark.asyncio
async def test_provision_all_users_on_demand_in_app_no_groups(mock_get_assigned_groups, mock_get_sync_job_id, mock_get_sp_id, mock_graph_service_client, caplog):
    await scim_syncer.provision_all_users_on_demand_in_app(mock_graph_service_client, TEST_APP_ID)
    expected_log_message = f"No groups assigned to the application (App ID: {TEST_APP_ID}, SP ID: {TEST_SP_ID}). Nothing to provision on demand."
    assert expected_log_message in caplog.text

# --- Tests for Main Entry Point ---

# Remove the old exec-based tests:
# def test_main_entry_point_runs_main(...)
# def test_main_entry_point_runs_on_demand(...)

# Add new tests for cli_entry_point
@pytest.mark.asyncio
@patch("scim_syncer.main", new_callable=AsyncMock) # Mock the target function
@patch.dict(os.environ, {"RUN_ON_DEMAND_PROVISIONING": "false"}, clear=True) # Ensure only this var is set for the test
async def test_cli_entry_point_runs_main(mock_main_func, caplog):
    """Tests that cli_entry_point calls main() when RUN_ON_DEMAND_PROVISIONING is false."""
    await scim_syncer.cli_entry_point()
    mock_main_func.assert_awaited_once()
    assert "Running main synchronization job." in caplog.text

@pytest.mark.asyncio
@patch("scim_syncer.get_graph_client", new_callable=AsyncMock) # Mock dependency
@patch("scim_syncer.provision_all_users_on_demand_in_app", new_callable=AsyncMock) # Mock target function
@patch.dict(os.environ, {"RUN_ON_DEMAND_PROVISIONING": "true", "AZURE_APP_ID": TEST_APP_ID}, clear=True) # Set env vars for this test
async def test_cli_entry_point_runs_on_demand(mock_on_demand_func, mock_get_graph_client, caplog):
    """Tests that cli_entry_point calls provision_all_users_on_demand_in_app when RUN_ON_DEMAND_PROVISIONING is true."""
    mock_client = AsyncMock(name="MockGraphClientForDemand")
    mock_get_graph_client.return_value = mock_client

    await scim_syncer.cli_entry_point()
    
    mock_get_graph_client.assert_awaited_once()
    mock_on_demand_func.assert_awaited_once_with(mock_client, TEST_APP_ID)
    assert "RUN_ON_DEMAND_PROVISIONING is true, running on-demand sync." in caplog.text

@pytest.mark.asyncio
@patch("scim_syncer.get_graph_client", new_callable=AsyncMock)
@patch("scim_syncer.provision_all_users_on_demand_in_app", new_callable=AsyncMock)
@patch.dict(os.environ, {"RUN_ON_DEMAND_PROVISIONING": "true"}, clear=True) # AZURE_APP_ID is MISSING
async def test_cli_entry_point_on_demand_missing_app_id(mock_on_demand_func, mock_get_graph_client, caplog):
    """Tests cli_entry_point logs error and returns if AZURE_APP_ID is missing for on-demand."""
    await scim_syncer.cli_entry_point()
    
    mock_get_graph_client.assert_not_awaited()
    mock_on_demand_func.assert_not_awaited()
    assert "AZURE_APP_ID environment variable not set. Cannot run on-demand provisioning." in caplog.text