import pytest
from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.dryrun_results import DryrunResponse
from algosdk.encoding import encode_address
from beaker import sandbox, client

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

    # opt-in Borrower to Token
    txn = TransactionWithSigner(
        txn=transaction.AssetOptInTxn(borrower.address, sp, token),
        signer=borrower.signer,
    )
    atc = AtomicTransactionComposer()
    atc.add_transaction(txn)
    atc.execute(sandbox.get_algod_client(), 3).tx_ids[0]

    # opt-in Lender to NFT
    txn = TransactionWithSigner(
        txn=transaction.AssetOptInTxn(lender.address, sp, nft),
        signer=lender.signer,
    )
    atc = AtomicTransactionComposer()
    atc.add_transaction(txn)
    atc.execute(sandbox.get_algod_client(), 3).tx_ids[0]

    app_client.create()
    app_client.fund(200_000)
    
@pytest.fixture(scope="function")
def opt_app_in_nft():
    sp.fee = sp.min_fee * 2
    app_client.call("opt_app_in_nft", nft=nft, signer=borrower.signer, suggested_params=sp)


@pytest.fixture(scope="function")
def request_loan():
    global amount
    global duration
    global interest
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
    duration=100
    interest=1
    app_client.call(
        "request_loan", 
        token=token,
        amount=amount,
        duration=duration,
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
    app_client.call("repay_loan", loan=axfer, signer=borrower.signer, foreign_assets=[nft])

@pytest.fixture(scope="function")
def liquidate_loan():
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
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""
    # App has [] assets
    assert app_client.client.account_info(app_client.app_addr)["assets"] == []
    # Borrower has 1 NFT and 0 TOKENS
    assert app_client.client.account_info(borrower.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(borrower.address)["assets"][-2]["amount"] == 1
    assert app_client.client.account_info(borrower.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(borrower.address)["assets"][-1]["amount"] == 0
    # Lender has 0 NFT and 10 TOKENS
    assert app_client.client.account_info(lender.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(lender.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(lender.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(lender.address)["assets"][-1]["amount"] == 10

#############
# OptIn tests
#############

@pytest.mark.opt_app_in_nft
def test_opt_app_in_nft(create_app, opt_app_in_nft):
    state = app_client.get_global_state()
    print(f"opt_app_in_nft: {state}\n")
    # App has 0 NFT
    assert state["nft"] == nft
    assert app_client.client.account_info(app_client.app_addr)["assets"][-1]["asset-id"] == nft
    assert app_client.client.account_info(app_client.app_addr)["assets"][-1]["amount"] == 0
    # Borrower has 1 NFT and 0 TOKENS
    assert app_client.client.account_info(borrower.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(borrower.address)["assets"][-2]["amount"] == 1
    assert app_client.client.account_info(borrower.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(borrower.address)["assets"][-1]["amount"] == 0
    # Lender has 0 NFT and 10 TOKENS
    assert app_client.client.account_info(lender.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(lender.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(lender.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(lender.address)["assets"][-1]["amount"] == 10


#####################
# request_loan tests
#####################

@pytest.mark.request_loan
def test_request_loan(create_app, opt_app_in_nft, request_loan):
    state = app_client.get_global_state()
    print(f"request_loan: {state}\n")
    assert state["token"] == token
    assert state["amount"] == amount
    assert state["duration"] == duration
    assert state["interest"] == interest
    # App has 1 NFT
    assert app_client.client.account_info(app_client.app_addr)["assets"][-1]["asset-id"] == nft
    assert app_client.client.account_info(app_client.app_addr)["assets"][-1]["amount"] == 1
    # Borrower has 0 NFT and 0 TOKENS
    assert app_client.client.account_info(borrower.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(borrower.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(borrower.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(borrower.address)["assets"][-1]["amount"] == 0
    # Lender has 0 NFT and 10 TOKENS
    assert app_client.client.account_info(lender.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(lender.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(lender.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(lender.address)["assets"][-1]["amount"] == 10
    
######################
# delete_request tests
######################

@pytest.mark.delete_request
def test_delete_request(create_app, opt_app_in_nft, request_loan, delete_request):
    state = app_client.get_global_state()
    print(f"delete_request: {state}\n")
    assert state["nft"] == 0
    assert state["token"] == 0
    assert state["amount"] == 0
    assert state["interest"] == 0
    assert state["start"] == 0
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""
    # App has [] assets
    assert app_client.client.account_info(app_client.app_addr)["assets"] == []
    # Borrower has 1 NFT and 0 TOKENS
    assert app_client.client.account_info(borrower.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(borrower.address)["assets"][-2]["amount"] == 1
    assert app_client.client.account_info(borrower.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(borrower.address)["assets"][-1]["amount"] == 0
    # Lender has 0 NFT and 10 TOKENS
    assert app_client.client.account_info(lender.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(lender.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(lender.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(lender.address)["assets"][-1]["amount"] == 10

###################
# accept_loan tests
###################

@pytest.mark.accept_loan
def test_accept_loan(create_app, opt_app_in_nft, request_loan, accept_loan):
    state = app_client.get_global_state()
    print(f"accept_loan: {state}\n")
    assert encode_address(bytes.fromhex(state["lender"])) == lender.address
    # App has 1 NFT
    assert app_client.client.account_info(app_client.app_addr)["assets"][-1]["asset-id"] == nft
    assert app_client.client.account_info(app_client.app_addr)["assets"][-1]["amount"] == 1
    # Borrower has 0 NFT and 5 TOKENS
    assert app_client.client.account_info(borrower.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(borrower.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(borrower.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(borrower.address)["assets"][-1]["amount"] == 5
    # Lender has 0 NFT and 5 TOKENS
    assert app_client.client.account_info(lender.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(lender.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(lender.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(lender.address)["assets"][-1]["amount"] == 5

##################
# repay_loan tests
##################

@pytest.mark.repay_loan
def test_repay_loan(create_app, opt_app_in_nft, request_loan, accept_loan, repay_loan):
    state = app_client.get_global_state()
    print(f"repay_loan: {state}\n")
    assert state["nft"] == 0
    assert state["token"] == 0
    assert state["amount"] == 0
    assert state["interest"] == 0
    assert state["start"] == 0
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""
    # App has [] assets
    assert app_client.client.account_info(app_client.app_addr)["assets"] == []
    # Borrower has 1 NFT and 0 TOKENS
    assert app_client.client.account_info(borrower.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(borrower.address)["assets"][-2]["amount"] == 1
    assert app_client.client.account_info(borrower.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(borrower.address)["assets"][-1]["amount"] == 0
    # Lender has 0 NFT and 10 TOKENS
    assert app_client.client.account_info(lender.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(lender.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(lender.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(lender.address)["assets"][-1]["amount"] == 10

##################
# repay_loan tests
##################

@pytest.mark.liquidate_loan
def test_liquidate_loan(create_app, opt_app_in_nft, request_loan, accept_loan, liquidate_loan):
    state = app_client.get_global_state()
    print(f"liquidate_loan: {state}\n")
    assert state["nft"] == 0
    assert state["token"] == 0
    assert state["amount"] == 0
    assert state["interest"] == 0
    assert state["start"] == 0
    assert state["duration"] == 0
    assert state["borrower"] == ""
    assert state["lender"] == ""
    # App has [] assets
    assert app_client.client.account_info(app_client.app_addr)["assets"] == []
    # Borrower has 0 NFT and 5 TOKENS
    assert app_client.client.account_info(borrower.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(borrower.address)["assets"][-2]["amount"] == 0
    assert app_client.client.account_info(borrower.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(borrower.address)["assets"][-1]["amount"] == 5
    # Lender has 1 NFT and 5 TOKENS
    assert app_client.client.account_info(lender.address)["assets"][-2]["asset-id"] == nft
    assert app_client.client.account_info(lender.address)["assets"][-2]["amount"] == 1
    assert app_client.client.account_info(lender.address)["assets"][-1]["asset-id"] == token
    assert app_client.client.account_info(lender.address)["assets"][-1]["amount"] == 5

