import pytest
from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.dryrun_results import DryrunResponse
from algosdk.encoding import encode_address
from beaker import *

##########
# fixtures
##########


@pytest.fixture(scope="function")
def create_app():
    global accounts
    global creator
    global borrower
    global lender
    global app_client
    global sp
    accounts = sorted(
        sandbox.get_accounts(),
        key=lambda a: sandbox.clients.get_algod_client().account_info(a.address)[
            "amount"
        ],
    )

    creator = accounts.pop()
    borrower = accounts.pop()
    lender = accounts.pop()

    app_client = client.ApplicationClient(
        app=open("./artifacts/application.json").read(),
        client=sandbox.get_algod_client(),
        signer=creator.signer,
    )
    sp=app_client.get_suggested_params()

    app_client.create()
    app_client.fund(200_000)

    # Borrower creates 1 NFT
    global nft
    atc = AtomicTransactionComposer()
    sp.fee = sp.min_fee
    nft_create = TransactionWithSigner(
        txn=transaction.AssetCreateTxn(
            sender=borrower.address,
            total=1,
            decimals=0,
            default_frozen=False,
            unit_name="NFT",
            asset_name="Beaker NFT",
            sp=sp,
        ),
        signer=borrower.signer,
    )
    atc.add_transaction(nft_create)
    tx_id = atc.execute(sandbox.get_algod_client(), 3).tx_ids[0]
    nft = sandbox.get_algod_client().pending_transaction_info(tx_id)["asset-index"]

    # Lender creates 10 Tokens
    global token
    atc = AtomicTransactionComposer()
    sp.fee = sp.min_fee * 2
    token_create = TransactionWithSigner(
        txn=transaction.AssetCreateTxn(
            sender=lender.address,
            total=10,
            decimals=0,
            default_frozen=False,
            unit_name="TOKEN",
            asset_name="Beaker TOKEN",
            sp=sp,
        ),
        signer=lender.signer,
    )
    atc.add_transaction(token_create)
    tx_id = atc.execute(sandbox.get_algod_client(), 3).tx_ids[0]
    token = sandbox.get_algod_client().pending_transaction_info(tx_id)["asset-index"]
    
@pytest.fixture(scope="function")
def opt_in_borrower():
    # opt-in Borrower to Token
    txn = TransactionWithSigner(
        txn=transaction.AssetOptInTxn(borrower.address, sp, token),
        signer=borrower.signer,
    )
    atc = AtomicTransactionComposer()
    atc.add_transaction(txn)
    tx_id = atc.execute(sandbox.get_algod_client(), 3).tx_ids[0]
    app_client.call("opt_in_borrower", signer=borrower.signer, suggested_params=sp)


@pytest.fixture(scope="function")
def opt_in_nft():
    sp.fee = sp.min_fee * 2
    app_client.call("opt_in_nft", nft=nft, signer=borrower.signer, suggested_params=sp)


@pytest.fixture(scope="function")
def request_loan():
    global amount
    # Borrower transfers the NFT
    sp.fee = sp.min_fee
    axfer = TransactionWithSigner(
        txn=transaction.AssetTransferTxn(
            sender=borrower.address,
            receiver=app_client.app_addr,
            index=nft,
            amt=1,
            sp=sp,
        ),
        signer=borrower.signer,
    )

    amount=5
    app_client.call(
        "request_loan", 
        token=token,
        amount=amount,
        duration=1,
        interest=1,
        axfer=axfer,
        signer=borrower.signer)

@pytest.fixture(scope="function")
def delete_request():
    sp.fee = sp.min_fee * 2
    app_client.call("delete_request", signer=borrower.signer, foreign_assets=[nft], suggested_params=sp)

@pytest.fixture(scope="function")
def accept_loan():
    # Lender transfers the Tokens
    axfer = TransactionWithSigner(
        txn=transaction.AssetTransferTxn(
            sender=lender.address,
            receiver=borrower.address,
            index=token,
            amt=amount,
            sp=sp,
        ),
        signer=lender.signer,
    )
    app_client.call("accept_loan", loan=axfer, signer=lender.signer)

@pytest.fixture(scope="function")
def repay_loan():
    # Borrower transfers the Tokens back to the Lender
    axfer = TransactionWithSigner(
        txn=transaction.AssetTransferTxn(
            sender=borrower.address,
            receiver=lender.address,
            index=token,
            amt=amount, # TODO: fix interest + interest * (latest_timestamp - start) / 31556926
            sp=sp,
        ),
        signer=borrower.signer,
    )
    app_client.call("repay_loan", loan=axfer, signer=borrower.signer)

@pytest.fixture(scope="function")
def liquidate_loan():
    # opt-in Lender to NFTs
    txn = TransactionWithSigner(
        txn=transaction.AssetOptInTxn(lender.address, sp, nft),
        signer=lender.signer,
    )
    atc = AtomicTransactionComposer()
    atc.add_transaction(txn)
    tx_id = atc.execute(sandbox.get_algod_client(), 3).tx_ids[0]
    sp.fee = sp.min_fee * 2
    app_client.call("liquidate_loan", signer=lender.signer, foreign_assets=[nft], suggested_params=sp)


##############
# create tests
##############


@pytest.mark.create
def test_create_state(create_app):
    state = app_client.get_global_state()
    print(f"create: {state}\n")
    assert state["nft"] == 0
    assert state["token"] == 0
    assert state["amount"] == 0
    assert state["interest"] == 0
    assert state["start"] == 0
    assert state["end"] == 0
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""

#############
# OptIn tests
#############

@pytest.mark.opt_in_borrower
def test_opt_in_borrower(create_app, opt_in_borrower):
    state = app_client.get_global_state()
    print(f"opt_in_borrower: {state}\n")
    assert state["borrower"] != ""

@pytest.mark.opt_in_nft
def test_opt_in_nft(create_app, opt_in_borrower, opt_in_nft):
    state = app_client.get_global_state()
    print(f"opt_in_nft: {state}\n")
    assert len(app_client.client.account_info(app_client.app_addr)["assets"]) == 1
    assert state["nft"] != 0


#####################
# request_loan tests
#####################

@pytest.mark.request_loan
def test_request_loan(create_app, opt_in_borrower, opt_in_nft, request_loan):
    state = app_client.get_global_state()
    print(f"request_loan: {state}\n")
    assert state["token"] != 0
    assert state["amount"] != 0
    assert state["duration"] != 0
    assert state["interest"] != 0
    
######################
# delete_request tests
######################

@pytest.mark.delete_request
def test_delete_request(create_app, opt_in_borrower, opt_in_nft, request_loan, delete_request):
    state = app_client.get_global_state()
    print(f"delete_request: {state}\n")
    assert state["nft"] == 0
    assert state["token"] == 0
    assert state["amount"] == 0
    assert state["interest"] == 0
    assert state["start"] == 0
    assert state["end"] == 0
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""

###################
# accept_loan tests
###################

@pytest.mark.accept_loan
def test_accept_loan(create_app, opt_in_borrower, opt_in_nft, request_loan, accept_loan):
    state = app_client.get_global_state()
    print(f"accept_loan: {state}\n")
    assert state["lender"] != ""
    assert state["start"] != 0
    assert state["end"] != 0

##################
# repay_loan tests
##################

@pytest.mark.repay_loan
def test_repay_loan(create_app, opt_in_borrower, opt_in_nft, request_loan, accept_loan, repay_loan):
    state = app_client.get_global_state()
    print(f"repay_loan: {state}\n")
    assert state["nft"] == 0
    assert state["token"] == 0
    assert state["amount"] == 0
    assert state["interest"] == 0
    assert state["start"] == 0
    assert state["end"] == 0
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""

##################
# repay_loan tests
##################

@pytest.mark.liquidate_loan
def test_liquidate_loan(create_app, opt_in_borrower, opt_in_nft, request_loan, accept_loan, liquidate_loan):
    state = app_client.get_global_state()
    print(f"liquidate_loan: {state}\n")
    assert state["nft"] == 0
    assert state["token"] == 0
    assert state["amount"] == 0
    assert state["interest"] == 0
    assert state["start"] == 0
    assert state["end"] == 0
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""
