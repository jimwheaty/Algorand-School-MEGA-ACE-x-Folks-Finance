from pyteal import *


def close_remainder_and_rekey_check() -> Expr:
    return Seq(
        Assert(Txn.close_remainder_to() == Global.zero_address()),
        Assert(Txn.rekey_to() == Global.zero_address()),
    )


def close_remainder_asset_close_and_rekey_check_of(txn: TxnObject) -> Expr:
    return Seq(
        Assert(txn.asset_close_to() == Global.zero_address()),
        Assert(txn.close_remainder_to() == Global.zero_address()),
        Assert(txn.rekey_to() == Global.zero_address()),
    )
