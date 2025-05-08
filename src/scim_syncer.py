import logging
import os
import sys

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from msgraph import GraphServiceClient
from msgraph.generated.models.o_data_errors.o_data_error import ODataError

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Configuration
# AZURE_APP_ID = os.getenv("AZURE_APP_ID") # Remove global assignment


async def get_graph_client() -> GraphServiceClient:
    """
    Initializes and returns a Microsoft GraphServiceClient using DefaultAzureCredential.

    Returns:
        GraphServiceClient: An initialized Microsoft Graph client.
    """
    logger.info("Authenticating with Azure using DefaultAzureCredential.")
    try:
        credential = DefaultAzureCredential()
        scopes = ["https://graph.microsoft.com/.default"]
        graph_client = GraphServiceClient(credentials=credential, scopes=scopes)
        logger.info("Successfully authenticated and Graph client created.")
        return graph_client
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise


async def get_service_principal_id(
    graph_client: GraphServiceClient, app_id: str
) -> str | None:
    """
    Retrieves the object ID of the service principal for a given application (client) ID.

    Args:
        graph_client: The Microsoft Graph client.
        app_id: The application (client) ID of the enterprise application.

    Returns:
        str | None: The object ID of the service principal, or None if not found.
    """
    logger.info(f"Retrieving service principal for app ID: {app_id}")
    try:
        # The filter should be on appId, not displayName
        service_principals = await graph_client.service_principals.get(
            request_configuration=lambda request_config: (
                request_config.query_parameters.filter(f"appId eq '{app_id}'"),
                request_config.query_parameters.select(["id", "appId"]),
            )
        )
        if service_principals and service_principals.value:
            sp_id = service_principals.value[0].id
            logger.info(f"Found service principal ID: {sp_id}")
            return sp_id
        else:
            logger.warning(f"Service principal not found for app ID: {app_id}")
            return None
    except ODataError as o_data_error:
        logger.error(f"OData error retrieving service principal: {o_data_error.error.message}")
        raise
    except Exception as e:
        logger.error(f"Error retrieving service principal: {e}")
        raise


async def get_synchronization_job_id(
    graph_client: GraphServiceClient, service_principal_id: str
) -> str | None:
    """
    Retrieves the ID of the SCIM synchronization job for a given service principal.
    It assumes the first active job is the one to use.

    Args:
        graph_client: The Microsoft Graph client.
        service_principal_id: The object ID of the service principal.

    Returns:
        str | None: The ID of the synchronization job, or None if not found.
    """
    logger.info(
        f"Retrieving synchronization jobs for service principal ID: {service_principal_id}"
    )
    try:
        jobs_response = (
            await graph_client.service_principals.by_service_principal_id(
                service_principal_id
            )
            .synchronization.jobs.get()
        )
        if jobs_response and jobs_response.value:
            # Assuming the first job is the SCIM provisioning job.
            # Add logic here to select the correct job if multiple exist,
            # e.g., by checking job.template_id or job.schedule.status == "Active"
            job_id = jobs_response.value[0].id
            logger.info(f"Found synchronization job ID: {job_id}")
            return job_id
        else:
            logger.warning(
                f"No synchronization jobs found for service principal ID: {service_principal_id}"
            )
            return None
    except ODataError as o_data_error:
        logger.error(
            f"OData error retrieving synchronization jobs: {o_data_error.error.message}"
        )
        raise
    except Exception as e:
        logger.error(f"Error retrieving synchronization jobs: {e}")
        raise


async def start_synchronization_job(
    graph_client: GraphServiceClient, service_principal_id: str, job_id: str
) -> None:
    """
    Starts a specific synchronization job for a service principal.

    Args:
        graph_client: The Microsoft Graph client.
        service_principal_id: The object ID of the service principal.
        job_id: The ID of the synchronization job to start.
    """
    logger.info(
        f"Starting synchronization job ID: {job_id} for service principal ID: {service_principal_id}"
    )
    try:
        # The StartPostRequestBody is empty as per typical SDK usage for this action.
        # If the SDK expects a specific structure not documented, this might need adjustment.
        await graph_client.service_principals.by_service_principal_id(
            service_principal_id
        ).synchronization.jobs.by_synchronization_job_id(job_id).start.post()
        logger.info(f"Successfully initiated synchronization job ID: {job_id}")
    except ODataError as o_data_error:
        logger.error(
            f"OData error starting synchronization job: {o_data_error.error.message}"
        )
        raise
    except Exception as e:
        logger.error(f"Error starting synchronization job: {e}")
        raise


async def main():
    """
    Main function to orchestrate SCIM provisioning.
    """
    logger.info("Starting SCIM provisioning process.")
    graph_client = None
    try:
        # Get AZURE_APP_ID inside the function
        app_id_to_sync = os.getenv("AZURE_APP_ID")
        if not app_id_to_sync:
            logger.error("AZURE_APP_ID environment variable not set. Cannot run main sync.")
            return

        graph_client = await get_graph_client()

        service_principal_id = await get_service_principal_id(
            graph_client, app_id_to_sync # Use local variable
        )
        if not service_principal_id:
            logger.error(
                f"Could not find service principal for app ID {app_id_to_sync}. Exiting."
            )
            return

        job_id = await get_synchronization_job_id(graph_client, service_principal_id)
        if not job_id:
            logger.error(
                f"Could not find synchronization job for service principal ID {service_principal_id}. Exiting."
            )
            return

        await start_synchronization_job(graph_client, service_principal_id, job_id)
        logger.info("SCIM provisioning process completed successfully.")

    except Exception as e:
        logger.error(f"An error occurred during the SCIM provisioning process: {e}")
    finally:
        if graph_client:
            # No explicit close/dispose method in msgraph-sdk-python v1 for GraphServiceClient
            # Connections are managed by the underlying HTTP client (e.g., httpx)
            logger.info("Graph client does not require explicit closing.")


# Optional: Functions for provisionOnDemand (as requested in prompt)
# These are not part of the main workflow but can be used for targeted provisioning.

async def get_assigned_groups(graph_client: GraphServiceClient, service_principal_id: str) -> list[str]:
    """
    Retrieves IDs of groups assigned to the enterprise application.

    Args:
        graph_client: The Microsoft Graph client.
        service_principal_id: The object ID of the service principal.

    Returns:
        list[str]: A list of group IDs.
    """
    logger.info(f"Retrieving assigned groups for service principal ID: {service_principal_id}")
    group_ids: list[str] = []
    try:
        # Using appRoleAssignedTo to find assignments to this SP
        assignments = await graph_client.service_principals.by_service_principal_id(service_principal_id).app_role_assigned_to.get(
            request_configuration=lambda request_config: (
                request_config.query_parameters.filter("principalType eq 'Group'"),
                request_config.query_parameters.select(["principalId"]) # Select only the principalId (group id)
            )
        )
        if assignments and assignments.value:
            for assignment in assignments.value:
                if assignment.principal_id:
                    group_ids.append(assignment.principal_id)
            logger.info(f"Found assigned group IDs: {group_ids}")
        else:
            logger.info(f"No groups found assigned to service principal ID: {service_principal_id}")
        return group_ids
    except ODataError as o_data_error:
        logger.error(f"OData error retrieving assigned groups: {o_data_error.error.message}")
        raise
    except Exception as e:
        logger.error(f"Error retrieving assigned groups: {e}")
        raise


async def get_group_members(graph_client: GraphServiceClient, group_id: str) -> list[str]:
    """
    Retrieves user IDs of members in a specific group.

    Args:
        graph_client: The Microsoft Graph client.
        group_id: The ID of the group.

    Returns:
        list[str]: A list of user IDs.
    """
    logger.info(f"Retrieving members for group ID: {group_id}")
    user_ids: list[str] = []
    try:
        members = await graph_client.groups.by_group_id(group_id).members.get(
            request_configuration=lambda request_config: (
                request_config.query_parameters.select(["id"]) # Select only user IDs
            )
        )
        # The response can contain different types of directoryObject, filter for users
        # However, /members endpoint by default returns users, groups, devices.
        # For provisionOnDemand, we typically need user objects.
        # Assuming direct members are users for simplicity here.
        # A more robust solution would check '@odata.type' == '#microsoft.graph.user'
        if members and members.value:
            for member in members.value:
                if member.id: #  and member.odata_type == "#microsoft.graph.user": (add if needed)
                    user_ids.append(member.id)
            logger.info(f"Found user IDs in group {group_id}: {user_ids}")
        else:
            logger.info(f"No members found in group ID: {group_id}")
        return user_ids
    except ODataError as o_data_error:
        logger.error(f"OData error retrieving group members: {o_data_error.error.message}")
        raise
    except Exception as e:
        logger.error(f"Error retrieving group members: {e}")
        raise

async def provision_user_on_demand(
    graph_client: GraphServiceClient,
    service_principal_id: str,
    job_id: str,
    user_id: str,
    rule_id: str = "", # Often SCIM/AD2SCIM
):
    """
    Triggers on-demand provisioning for a specific user.

    Args:
        graph_client: The Microsoft Graph client.
        service_principal_id: The object ID of the service principal.
        job_id: The ID of the synchronization job.
        user_id: The ID of the user to provision.
        rule_id: The identifier of the synchronization rule to use.
                 Commonly "SCIM" or the specific AD to SCIM connector's rule.
                 This might need to be discovered from the synchronization schema.
                 Forcing a default if not provided.
    """
    logger.info(
        f"Triggering provisionOnDemand for user ID: {user_id} in job ID: {job_id}"
    )

    # The API expects a list of parameters.
    # The '#microsoft.graph.synchronizationJobApplicationParameters' is a type hint for the API.
    # We need to construct a list of SynchronizationJobApplicationParameters objects.
    # Each parameter has 'name' and 'value' (which is a string).
    # 'objectId' is the user's ID, 'subjectId' is also user's ID in this context.
    # 'attributes' could be used to pass specific attributes for provisioning if needed.
    # 'ruleId' is crucial. Defaulting to "SCIM" might work for some, but often it's specific.
    # Example: ruleId = "ActiveDirectory->SCIM"
    # This might require inspecting the job's schema to get the correct ruleId.

    # Simplified payload for provisionOnDemand
    # Adjust `parameters` if a more complex structure or specific ruleId is needed.
    from msgraph.generated.models.synchronization_job_application_parameters import SynchronizationJobApplicationParameters
    from msgraph.generated.models.synchronization_job_subject import SynchronizationJobSubject

    subject = SynchronizationJobSubject(
        object_id=user_id,
        object_type_name="User" # Or appropriate type if not User
    )

    try:
        await graph_client.service_principals.by_service_principal_id(
            service_principal_id
        ).synchronization.jobs.by_synchronization_job_id(
            job_id
        ).provision_on_demand.post(body=subject) # Pass the subject directly
        logger.info(f"Successfully triggered provisionOnDemand for user ID: {user_id}")
    except ODataError as o_data_error:
        logger.error(
            f"OData error during provisionOnDemand for user {user_id}: {o_data_error.error.message}"
        )
        raise
    except Exception as e:
        logger.error(f"Error during provisionOnDemand for user {user_id}: {e}")
        raise

async def provision_all_users_on_demand_in_app(graph_client: GraphServiceClient, app_id: str):
    """
    Orchestrates on-demand provisioning for all users in all groups assigned to an application.
    This is an example of using the optional functions.
    """
    logger.info(f"Starting on-demand provisioning for all users in app ID: {app_id}")
    # Note: app_id is passed directly to this function, no need to getenv here
    service_principal_id = await get_service_principal_id(graph_client, app_id)
    if not service_principal_id:
        logger.error(f"Cannot perform on-demand provisioning: Service principal not found for app {app_id}.")
        return

    job_id = await get_synchronization_job_id(graph_client, service_principal_id)
    if not job_id:
        logger.error(f"Cannot perform on-demand provisioning: Sync job not found for SP {service_principal_id}.")
        return

    # Discover a valid ruleId from the schema (example, might need adjustment)
    # rule_id_to_use = "SCIM" # Default, or discover dynamically
    # try:
    #     schema = await graph_client.service_principals.by_service_principal_id(service_principal_id).synchronization.schema.get()
    #     if schema and schema.synchronization_rules:
    #         for rule in schema.synchronization_rules:
    #             if rule.name and "user" in rule.name.lower() and rule.id: # Example logic
    #                 rule_id_to_use = rule.id
    #                 logger.info(f"Using discovered ruleId: {rule_id_to_use}")
    #                 break
    # except Exception as e:
    #     logger.warning(f"Could not discover ruleId, using default. Error: {e}")


    assigned_group_ids = await get_assigned_groups(graph_client, service_principal_id)
    if not assigned_group_ids:
        logger.info("No groups assigned to the application. Nothing to provision on demand.")
        return

    for group_id in assigned_group_ids:
        user_ids = await get_group_members(graph_client, group_id)
        for user_id in user_ids:
            try:
                await provision_user_on_demand(
                    graph_client,
                    service_principal_id,
                    job_id,
                    user_id,
                    # rule_id=rule_id_to_use # Pass the discovered or default ruleId
                )
            except Exception as e:
                logger.error(f"Failed to provision user {user_id} on demand. Error: {e}")
    logger.info(f"Completed on-demand provisioning for users in app ID: {app_id}")

async def cli_entry_point():
    """Determines which workflow to run based on environment variables."""
    if os.getenv("RUN_ON_DEMAND_PROVISIONING", "false").lower() == "true":
        logger.info("RUN_ON_DEMAND_PROVISIONING is true, running on-demand sync.")
        # Get AZURE_APP_ID inside the function where it's needed for this branch
        app_id_for_demand = os.getenv("AZURE_APP_ID")
        if not app_id_for_demand:
            logger.error("AZURE_APP_ID environment variable not set. Cannot run on-demand provisioning.")
            return
        try:
            client = await get_graph_client()
            await provision_all_users_on_demand_in_app(client, app_id_for_demand) # Use local variable
        except Exception as e:
             logger.error(f"An error occurred during the on-demand provisioning process: {e}")
             # Decide if you want to exit with error code here or just log
    else:
        logger.info("Running main synchronization job.")
        # main() now fetches AZURE_APP_ID internally
        await main()

if __name__ == "__main__":
    import asyncio
    # Run the new entry point function
    asyncio.run(cli_entry_point()) 