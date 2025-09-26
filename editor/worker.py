# editor/worker.py

import logging
import shutil
import os

# This worker needs access to the baker and the package_builder.
from editor.baker import bake_master_data
from editor.package_builder import chunk_master_data

def bake_and_chunk_worker(generator_settings: dict, logger: logging.Logger):
    """
    A worker function that first bakes the master data, then chunks it,
    and finally cleans up the temporary master data.
    """
    master_data_path = None # Initialize to ensure it exists in the finally block
    try:
        logger.info("WORKER: Starting master bake...")
        # Capture the actual path created by the baker
        master_data_path = bake_master_data(generator_settings, logger)
        
        logger.info(f"WORKER: Master bake complete at '{master_data_path}'. Starting chunking...")
        # Use the captured path for chunking
        chunk_master_data(master_data_path, logger)
        logger.info("WORKER: Chunking complete.")
            
        return True
    except Exception as e:
        # Use exc_info=True to log the full traceback from the worker process
        logger.critical(f"WORKER: An exception occurred during bake/chunk process: {e}", exc_info=True)
        if master_data_path:
             logger.warning(f"WORKER: The intermediate master data at '{master_data_path}' was NOT deleted due to an error.")
        return False
    finally:
        # --- Cleanup Step ---
        # This 'finally' block ensures cleanup happens even if chunking succeeds.
        # We check if the path was successfully created before trying to delete it.
        if master_data_path and os.path.exists(master_data_path):
            logger.info(f"WORKER: Cleaning up temporary master data at '{master_data_path}'...")
            shutil.rmtree(master_data_path)
            logger.info("WORKER: Cleanup complete.")