#!/usr/bin/env python3

from typing import Final

from beaker import *
from pyteal import *


class State:
    collateral_id: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="ID of the NFT",
    )

    borrowing_id: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="ID of the token requested to borrow",
    )

    amount: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Amount of tokens requested to borrow",
    )

    interest: Final[GlobalStateValue] = GlobalStateValue(  # 2 decimal points
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Amount of interest the borrower asks for (uALGO)",
    )

    start: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Timestamp that the loan started",
    )

    duration: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Duration that the loan is valid",
    )

    lender: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        default=Bytes(""),
        descr="ID of the lender",
    )


app = Application("NFTasCollateral", state=State)


@app.create(bare=True)
def create() -> Expr:
    # Set all global state to the default values
    return app.initialize_global_state()


# Only allow app creator to opt the app account into a NFT
@app.external(authorize=Authorize.only(Global.creator_address()))
def opt_in_nft(nft: abi.Asset) -> Expr:
    return Seq(
        # Verify a NFT hasn't already been opted into
        Assert(app.state.collateral_id == Int(0)),
        # Save ASA ID in global state
        app.state.collateral_id.set(nft.asset_id()),
        # Submit opt-in transaction: 0 asset transfer to self
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.fee: Int(0),  # cover fee with outer txn
                TxnField.asset_receiver: Global.current_application_address(),
                TxnField.xfer_asset: nft.asset_id(),
                TxnField.asset_amount: Int(0),
            }
        ),
    )


# Borrower
@app.external(authorize=Authorize.only(Global.creator_address()))
def request_loan(
    token: abi.Uint64,
    amount: abi.Uint64,
    duration: abi.Uint64,
    interest: abi.Uint64,
    axfer: abi.AssetTransferTransaction,
) -> Expr:
    return Seq(
        # Ensure the loan hasn't already been started
        Assert(app.state.borrowing_id.get() == Int(0)),
        # Verify axfer
        Assert(axfer.get().asset_receiver() == Global.current_application_address()),
        Assert(axfer.get().xfer_asset() == app.state.collateral_id),
        # Set global state
        app.state.borrowing_id.set(token.get()),
        app.state.amount.set(amount.get()),
        app.state.duration.set(duration.get()),
        app.state.interest.set(interest.get()),
    )


@app.delete
def delete_request() -> Expr:
    return Seq(
        Assert(app.state.lender.get() == Bytes("")),
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.fee: Int(0),  # cover fee with outer txn
                TxnField.receiver: Global.creator_address(),
                TxnField.xfer_asset: app.state.collateral_id.get(),
                # close_remainder_to to sends full balance, including 0.1 account MBR
                TxnField.close_remainder_to: Global.creator_address(),
                # we are closing the account, so amount can be zero
                TxnField.amount: Int(0),
            }
        ),
    )


@Subroutine(TealType.none)
def tranfer_token(receiver: Expr, token: Expr, amount: Expr) -> Expr:
    return InnerTxnBuilder.Execute(
        {
            TxnField.type_enum: TxnType.Payment,
            TxnField.xfer_asset: token,
            TxnField.receiver: receiver,
            TxnField.amount: amount,
            TxnField.fee: Int(0),  # cover fee with outer txn
        }
    )


@app.external(authorize=Authorize.only(Global.creator_address()))
def repay_loan() -> Expr:
    return Seq(
        # Auction end check is commented out for automated testing
        Assert(
            Global.latest_timestamp()
            <= app.state.start.get() + app.state.duration.get()
        ),
        amount := app.state.amount.get()
        + app.state.interest.get()
        * (
            (Global.latest_timestamp() - app.state.start.get()) / 31556926
        ),  # 1 year = 31 556 926 seconds
        tranfer_token(app.state.lender.get(), app.state.borrowing_id.get(), amount),
    )


# Lender
@app.external
def accept_loan(loan: abi.PaymentTransaction) -> Expr:
    return Seq(
        # Verify loan transaction
        Assert(app.state.lender == Bytes("")),
        Assert(loan.get().xfer_asset() == app.state.borrowing_id.get()),
        Assert(loan.get().amount() == app.state.amount.get()),
        Assert(Txn.sender() == loan.get().sender()),
        Assert(loan.get().receiver() == Global.creator_address()),
        # Set global state
        app.state.lender.set(loan.get().sender()),
        tranfer_token(
            Global.creator_address(),
            app.state.borrowing_id.get(),
            app.state.amount.get(),
        ),
    )


@app.external
def liquidate_loan(nft: abi.Asset, close_to_account: abi.Account) -> Expr:
    return Seq(
        # Auction end check is commented out for automated testing
        Assert(
            Global.latest_timestamp() > app.state.start.get() + app.state.duration.get()
        ),
        # Send ASA to highest bidder
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.fee: Int(0),  # cover fee with outer txn
                TxnField.xfer_asset: app.state.collateral_id,
                TxnField.asset_amount: Int(1),
                TxnField.asset_receiver: app.state.lender,
                TxnField.asset_close_to: close_to_account.address(),
            }
        ),
    )


if __name__ == "__main__":
    app.build().export()
