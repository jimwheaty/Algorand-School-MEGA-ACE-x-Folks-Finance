#!/usr/bin/env python3

from typing import Final

from beaker import *
from pyteal import *


class State:
    nft: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="ID of the NFT",
    )

    token: Final[GlobalStateValue] = GlobalStateValue(
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
        descr="Amount of interest the borrower asks for",
    )

    start: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Timestamp that the loan started",
    )

    end: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Timestamp that the loan is ended",
    )

    duration: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="How much time the borrower needs the loan for",
    )

    borrower: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        default=Bytes(""),
        descr="ID of the borrower",
    )

    lender: Final[GlobalStateValue] = GlobalStateValue(
        stack_type=TealType.bytes,
        default=Bytes(""),
        descr="ID of the lender",
    )


app = Application("NFTasCollateral", state=State)


@app.create(bare=True)
def create() -> Expr:
    # State
    return app.initialize_global_state()


# ---------------------------- Borrower ----------------------------
@app.external()
# @app.opt_in(bare=True)
def opt_in_borrower() -> Expr:
    return Seq(
        # Checks
        Assert(app.state.borrower == Bytes("")),
        # State
        app.state.borrower.set(Txn.sender())
    )


@app.external()
def opt_in_nft(nft: abi.Asset) -> Expr:
    return Seq(
        # Checks
        Assert(Txn.sender() == app.state.borrower),
        Assert(app.state.nft == Int(0)),
        # Transaction
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: nft.asset_id(),
                TxnField.asset_amount: Int(0),
                TxnField.asset_receiver: Global.current_application_address(),
                TxnField.fee: Int(0),
            }
        ),
        # State
        app.state.nft.set(nft.asset_id()),
    )


@app.external()
def request_loan(
    token: abi.Uint64,
    amount: abi.Uint64,
    duration: abi.Uint64,
    interest: abi.Uint64,
    axfer: abi.AssetTransferTransaction,
) -> Expr:
    return Seq(
        # Checks
        Assert(Txn.sender() == app.state.borrower),
        Assert(app.state.token.get() == Int(0)),
        Assert(axfer.get().asset_receiver() == Global.current_application_address()),
        Assert(axfer.get().xfer_asset() == app.state.nft),
        # State
        app.state.token.set(token.get()),
        app.state.amount.set(amount.get()),
        app.state.duration.set(duration.get()),
        app.state.interest.set(interest.get()),
    )


@app.external()
def delete_request() -> Expr:
    return Seq(
        # Checks
        Assert(Txn.sender() == app.state.borrower),
        Assert(app.state.lender == Bytes("")),
        # Transaction
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: app.state.nft,
                TxnField.asset_amount: Int(1),
                TxnField.asset_receiver: app.state.borrower.get(),
                TxnField.fee: Int(0),
                TxnField.asset_close_to: app.state.borrower.get(),
            }
        ),
        # State
        app.initialize_global_state()
    )


@app.external
def repay_loan(loan: abi.AssetTransferTransaction) -> Expr:
    return Seq(
        # Checks
        Assert(Txn.sender() == app.state.borrower),
        Assert(app.state.lender != Bytes("")),
        Assert(Global.latest_timestamp() <= app.state.end.get()),
        Assert(loan.get().xfer_asset() == app.state.token.get()),
        Assert(loan.get().asset_amount() == app.state.amount.get()),
        Assert(loan.get().asset_receiver() == app.state.lender.get()),
        # State
        app.initialize_global_state()
        # TODO: delete contract?
    )


# ---------------------------- Lender ----------------------------
@app.external
def accept_loan(loan: abi.AssetTransferTransaction) -> Expr:
    return Seq(
        # Checks
        Assert(app.state.lender == Bytes("")),
        Assert(loan.get().xfer_asset() == app.state.token.get()),
        Assert(loan.get().asset_amount() == app.state.amount.get()),
        Assert(loan.get().asset_receiver() == app.state.borrower.get()),
        # State
        app.state.lender.set(loan.get().sender()),
        app.state.start.set(Global.latest_timestamp()),
        app.state.end.set(Global.latest_timestamp() + app.state.duration.get()),
    )


@app.external
def liquidate_loan(close_to_account: abi.Account) -> Expr:
    return Seq(
        # Checks
        Assert(Txn.sender() == app.state.lender),
        Assert(
            Global.latest_timestamp() > app.state.end.get()
        ),
        # Transaction
        InnerTxnBuilder.Execute(
            {
                TxnField.type_enum: TxnType.AssetTransfer,
                TxnField.xfer_asset: app.state.nft,
                TxnField.asset_amount: Int(1),
                TxnField.asset_receiver: app.state.lender,
                TxnField.fee: Int(0),
                TxnField.asset_close_to: app.state.lender,
            }
        ),
        # TODO: delete contract?
        app.initialize_global_state()
    )

if __name__ == "__main__":
    app.build().export("./artifacts")
