import asyncio
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.identity.aio import DefaultAzureCredential # For async mocking
from msgraph import GraphServiceClient
from msgraph.generated.models import (
    ServicePrincipal, ServicePrincipalCollection, SynchronizationJob, SynchronizationJobCollection, AppRoleAssignment, AppRoleAssignmentCollection, User, DirectoryObjectCollection
)
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
    mock_client = AsyncMock(spec=GraphServiceClient)
    # Mock the fluent API structure
    mock_client.service_principals = AsyncMock()
    mock_client.service_principals.by_service_principal_id.return_value = AsyncMock()
    mock_client.service_principals.by_service_principal_id.return_value.synchronization = AsyncMock()
    mock_client.service_principals.by_service_principal_id.return_value.synchronization.jobs = AsyncMock()
    mock_client.service_principals.by_service_principal_id.return_value.synchronization.jobs.by_synchronization_job_id.return_value = AsyncMock()
    mock_client.service_principals.by_service_principal_id.return_value.synchronization.jobs.by_synchronization_job_id.return_value.start = AsyncMock()

    # For optional functions
    mock_client.service_principals.by_service_principal_id.return_value.app_role_assigned_to = AsyncMock()
    mock_client.groups = AsyncMock()
    mock_client.groups.by_group_id.return_value = AsyncMock()
    mock_client.groups.by_group_id.return_value.members = AsyncMock()
    mock_client.service_principals.by_service_principal_id.return_value.synchronization.jobs.by_synchronization_job_id.return_value.provision_on_demand = AsyncMock()
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
    sp_collection = ServicePrincipalCollection(value=[sp])
    mock_graph_service_client.service_principals.get.return_value = sp_collection

    sp_id = await scim_syncer.get_service_principal_id(mock_graph_service_client, TEST_APP_ID)

    mock_graph_service_client.service_principals.get.assert_called_once()
    args, kwargs = mock_graph_service_client.service_principals.get.call_args
    assert kwargs["request_configuration"].query_parameters.filter == f"appId eq '{TEST_APP_ID}'"
    assert sp_id == TEST_SP_ID

@pytest.mark.asyncio
async def test_get_service_principal_id_not_found(mock_graph_service_client):
    """Tests service principal not found."""
    sp_collection = ServicePrincipalCollection(value=[]) # Empty list
    mock_graph_service_client.service_principals.get.return_value = sp_collection

    sp_id = await scim_syncer.get_service_principal_id(mock_graph_service_client, TEST_APP_ID)
    assert sp_id is None

@pytest.mark.asyncio
async def test_get_service_principal_id_odata_error(mock_graph_service_client, caplog):
    """Tests ODataError during service principal retrieval."""
    error = ODataError(error=MainError(message="Test OData Error"))
    mock_graph_service_client.service_principals.get.side_effect = error

    with pytest.raises(ODataError):
        await scim_syncer.get_service_principal_id(mock_graph_service_client, TEST_APP_ID)
    assert "OData error retrieving service principal: Test OData Error" in caplog.text

@pytest.mark.asyncio
async def test_get_synchronization_job_id_success(mock_graph_service_client):
    """Tests successful retrieval of synchronization job ID."""
    job = SynchronizationJob(id=TEST_JOB_ID)
    job_collection = SynchronizationJobCollection(value=[job])
    # Correctly mock the fluent call chain for jobs
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.synchronization.jobs.get.return_value = job_collection

    job_id = await scim_syncer.get_synchronization_job_id(mock_graph_service_client, TEST_SP_ID)

    mock_graph_service_client.service_principals.by_service_principal_id.assert_called_with(TEST_SP_ID)
    mock_sp_item.synchronization.jobs.get.assert_called_once()
    assert job_id == TEST_JOB_ID

@pytest.mark.asyncio
async def test_get_synchronization_job_id_not_found(mock_graph_service_client):
    """Tests synchronization job not found."""
    job_collection = SynchronizationJobCollection(value=[])
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.synchronization.jobs.get.return_value = job_collection

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
    assert "OData error retrieving synchronization jobs: Job OData Error" in caplog.text

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
    assignment_collection = AppRoleAssignmentCollection(value=[assignment1])
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.app_role_assigned_to.get.return_value = assignment_collection

    group_ids = await scim_syncer.get_assigned_groups(mock_graph_service_client, TEST_SP_ID)
    assert group_ids == [TEST_GROUP_ID_1]
    mock_sp_item.app_role_assigned_to.get.assert_called_once()
    args, kwargs = mock_sp_item.app_role_assigned_to.get.call_args
    assert kwargs["request_configuration"].query_parameters.filter == "principalType eq 'Group'"

@pytest.mark.asyncio
async def test_get_assigned_groups_no_groups(mock_graph_service_client):
    """Tests retrieval when no groups are assigned."""
    assignment_collection = AppRoleAssignmentCollection(value=[])
    mock_sp_item = mock_graph_service_client.service_principals.by_service_principal_id.return_value
    mock_sp_item.app_role_assigned_to.get.return_value = assignment_collection

    group_ids = await scim_syncer.get_assigned_groups(mock_graph_service_client, TEST_SP_ID)
    assert group_ids == []

@pytest.mark.asyncio
async def test_get_group_members_success(mock_graph_service_client):
    """Tests successful retrieval of group members (users)."""
    user1 = User(id=TEST_USER_ID_1)
    # odata_type is usually @odata.type in actual responses, but the model property is odata_type
    user1.odata_type = "#microsoft.graph.user" # Important for filtering if done in code
    member_collection = DirectoryObjectCollection(value=[user1])
    mock_group_item = mock_graph_service_client.groups.by_group_id.return_value
    mock_group_item.members.get.return_value = member_collection

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
    mock_get_assigned_groups.return_value = [TEST_GROUP_ID_1]
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
    assert f"Completed on-demand provisioning for users in app ID: {TEST_APP_ID}" in caplog.text

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
    assert "No groups assigned to the application. Nothing to provision on demand." in caplog.text


@patch("asyncio.run")
@patch("scim_syncer.main")
@patch.dict(os.environ, {"RUN_ON_DEMAND_PROVISIONING": "false"})
def test_main_entry_point_runs_main(mock_main_func, mock_asyncio_run, caplog):
    # Temporarily remove the __main__ guard to test the entry point logic
    # This is a bit hacky, but necessary to test this part of the script
    original_name = scim_syncer.__name__
    scim_syncer.__name__ = "__main__"
    try:
        # Re-evaluate the if __name__ == "__main__": block by re-importing or exec
        # Using exec to re-run the bottom part of the script
        with open(os.path.join(src_path, "scim_syncer.py"), "r") as f:
            script_content = f.read()
        # Isolate the if __name__ == "__main__": block
        main_block = script_content[script_content.find('if __name__ == "__main__":'):]
        # Create a dictionary with the necessary mocks for the exec environment
        exec_globals = {
            "asyncio": asyncio,
            "os": os,
            "logger": scim_syncer.logger, # use the script's logger
            "main": mock_main_func, # mock for the main sync
            "get_graph_client": AsyncMock(), # mock for on-demand
            "provision_all_users_on_demand_in_app": AsyncMock(), # mock for on-demand
            "AZURE_APP_ID": TEST_APP_ID # Ensure AZURE_APP_ID is available
        }
        exec(main_block, exec_globals)

        mock_asyncio_run.assert_called_once_with(mock_main_func())
        assert "Running main synchronization job." in caplog.text
    finally:
        scim_syncer.__name__ = original_name # Restore original name

@patch("asyncio.run")
@patch("scim_syncer.provision_all_users_on_demand_in_app")
@patch("scim_syncer.get_graph_client") # Mock get_graph_client for on-demand
@patch.dict(os.environ, {"RUN_ON_DEMAND_PROVISIONING": "true", "AZURE_APP_ID": TEST_APP_ID})
def test_main_entry_point_runs_on_demand(mock_get_graph_client, mock_on_demand_func, mock_asyncio_run, caplog):
    original_name = scim_syncer.__name__
    scim_syncer.__name__ = "__main__"
    mock_graph_client_instance = AsyncMock()
    mock_get_graph_client.return_value = mock_graph_client_instance

    try:
        with open(os.path.join(src_path, "scim_syncer.py"), "r") as f:
            script_content = f.read()
        main_block = script_content[script_content.find('if __name__ == "__main__":'):]
        
        exec_globals = {
            "asyncio": asyncio,
            "os": os,
            "logger": scim_syncer.logger,
            "main": AsyncMock(), # Mock main, not used here
            "get_graph_client": mock_get_graph_client, # Use the patched mock
            "provision_all_users_on_demand_in_app": mock_on_demand_func,
            "AZURE_APP_ID": TEST_APP_ID
        }
        exec(main_block, exec_globals)
        
        # Check that asyncio.run was called with the on-demand workflow
        # The argument to asyncio.run will be the coroutine object
        # We need to check that the correct functions within that coroutine were called.
        # This is tricky as exec creates a new scope.
        # Instead, we check if the top-level on_demand function was called via the mock
        # and that the log message indicates on-demand mode.
        
        # The call to asyncio.run will be with an internal async function.
        # We need to ensure that this internal function, when run, calls our mocks.
        assert mock_asyncio_run.called
        # To verify the internal calls, we'd need to capture the coroutine passed to asyncio.run
        # and run it. For simplicity, we rely on the fact that if the log appears and
        # the on-demand function is configured to be called by `asyncio.run`, it implies correctness.
        # The `exec` makes direct assertion on `mock_on_demand_func.assert_called_once_with` hard.
        
        assert "RUN_ON_DEMAND_PROVISIONING is true, running on-demand sync." in caplog.text
        # Further check if `provision_all_users_on_demand_in_app` was intended to be called
        # by inspecting the mock_asyncio_run arguments if possible, or by checking side effects like logs.
        # Given the exec model, direct assertions on calls within the exec'd block are complex.
        # We can, however, assert that the `mock_on_demand_func` was called IF the structure inside exec allows it.

        # Need to manually run the coroutine passed to `asyncio.run` to test its internals
        # This is because the mock_on_demand_func is called *inside* the coroutine
        if mock_asyncio_run.call_args:
            coro_to_run = mock_asyncio_run.call_args[0][0]
            asyncio.run(coro_to_run) # Actually run the captured coroutine
            mock_get_graph_client.assert_called_once()
            mock_on_demand_func.assert_called_once_with(mock_graph_client_instance, TEST_APP_ID)

    finally:
        scim_syncer.__name__ = original_name


</rewritten_file>