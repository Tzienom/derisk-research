import logging

import pandas as pd
from time import monotonic
from handlers.loan_states.abstractions import LoanStateComputationBase
from handlers.loan_states.nostra_alpha.events import (
    NostraAlphaState,
    INTEREST_RATE_MODEL_ADDRESS,
    ADDRESSES_TO_EVENTS,
    EVENTS_METHODS_MAPPING,
)
from handler_tools.constants import ProtocolAddresses, ProtocolIDs, NOSTRA_EVENTS_MAPPING

logger = logging.getLogger(__name__)


class NostraAlphaStateComputation(LoanStateComputationBase):
    """
    A class that computes the loan states for the NOSTRA_ALPHA protocol.
    """

    PROTOCOL_TYPE = ProtocolIDs.NOSTRA_ALPHA.value
    PROTOCOL_ADDRESSES = ProtocolAddresses().NOSTRA_ALPHA_ADDRESSES
    INTEREST_RATES_KEYS = ["InterestStateUpdated"]
    EVENTS_MAPPING = NOSTRA_EVENTS_MAPPING
    EVENTS_METHODS_MAPPING = EVENTS_METHODS_MAPPING
    ADDRESSES_TO_EVENTS = ADDRESSES_TO_EVENTS

    def process_interest_rate_event(
        self, nostra_state: NostraAlphaState, event: pd.Series
    ) -> None:
        """
        Processes an interest rate event.

        :param nostra_state: The Nostra alpha state object.
        :type nostra_state: NostraAlphaState
        :param event: The data of the event.
        :type event: pd.Series
        """
        nostra_state.process_interest_rate_model_event(event)
        self.add_interest_rate_data(nostra_state, event)

    def process_data(self, data: list[dict]) -> pd.DataFrame:
        """
        Processes the data retrieved from the DeRisk API.
        This method must be implemented by subclasses to define the data processing steps.

        :param data: The data retrieved from the DeRisk API.
        :type data: list[dict]

        :return: pd.DataFrame
        """
        nostra_alpha_state = NostraAlphaState()

        events_with_interest_rate = (
            list(self.EVENTS_MAPPING.keys()) + self.INTEREST_RATES_KEYS
        )

        # Init DataFrame
        df = pd.DataFrame(data)
        df_filtered = df[df["key_name"].isin(events_with_interest_rate)]
        sorted_df = df_filtered.sort_values(["block_number", "id"])

        # Filter out events that are not in the mapping
        for index, row in sorted_df.iterrows():
            method_name = self.EVENTS_MAPPING.get(row["key_name"], "") or ""
            self.process_event(nostra_alpha_state, method_name, row)

        result_df = self.get_result_df(nostra_alpha_state.loan_entities)
        return result_df

    def process_event(
            self, instance_state: NostraAlphaState, method_name: str, event: pd.Series
    ) -> None:
        """
        Processes an event based on the method name and the event data.

        Updates the last block processed to ensure data consistency
        and calls the appropriate method to handle the event.

        :param instance_state: The instance of the state class to call the method on.
        :type instance_state: object
        :param method_name: The name of the method to call for processing the event.
        :param event: The event data as a pandas Series.
        """
        try:
            block_number = event.get("block_number")
            # For each block number, process the interest rate event
            if event["from_address"] == INTEREST_RATE_MODEL_ADDRESS:
                self.process_interest_rate_event(instance_state, event)
                return

            if block_number and block_number >= self.last_block:
                self.last_block = block_number
                event_type = self.ADDRESSES_TO_EVENTS[event["from_address"]]
                getattr(
                    instance_state, self.EVENTS_METHODS_MAPPING[(event_type, event["key_name"])]
                )(event=event)
        except Exception as e:
            logger.exception(f"Failed to process event due to an error: {e}")

    def run(self) -> None:
        """
        Runs the loan state computation for the specific protocol.
        """
        max_retries = 1000000  # FIXME remove this code only for first run
        retry = 0

        self.last_block = 10854 # FIXME first run

        logger.info(f"Default last block: {self.last_block}")
        while retry < max_retries:
            if self.last_block >= 647952: # FIXME last block
                logger.info(f"Reached the last block: {self.last_block}")
                break

            interest_rate_data = self.get_data(
                INTEREST_RATE_MODEL_ADDRESS, self.last_block
            )
            data = self.get_addresses_data(self.PROTOCOL_ADDRESSES, self.last_block)

            if not data:
                logger.info(f"No data for block {self.last_block}")
                self.last_block += self.PAGINATION_SIZE
                retry += 1
                continue

            # Process the data
            all_events_data = interest_rate_data + data
            processed_data = self.process_data(all_events_data)

            # Save the processed data and  interest rate data
            self.save_data(processed_data)
            self.save_interest_rate_data()

            # Update the last block
            self.last_block += self.PAGINATION_SIZE
            logger.info(f"Processed data up to block {self.last_block}")
            retry = 0  # Reset retry counter if data is found and processed

        if retry == max_retries:
            logger.info(f"Reached max retries for block: {self.last_block}")


def run_loan_states_computation_for_nostra_alpha() -> None:
    """
    Runs the NOSTRA_ALPHA loan state computation.
    """
    start = monotonic()
    logging.basicConfig(level=logging.INFO)

    logger.info("Starting NostraAlpha loan state computation")
    computation = NostraAlphaStateComputation()
    computation.run()

    logger.info(
        "Finished NostraAlpha  loan state computation, Time taken: %s seconds",
        monotonic() - start,
    )


if __name__ == "__main__":
    run_loan_states_computation_for_nostra_alpha()
