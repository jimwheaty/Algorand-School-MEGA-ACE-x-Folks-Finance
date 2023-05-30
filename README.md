# Algorand School MEGA-ACE x Folks Finance

## What is this?

### NFT as collateral Contract Development with PyTEAL

### Description:
Welcome to the NFT as collateral Contract Development task! Participants will showcase their skills and creativity by developing a smart contract using PyTEAL.

### Objective:
The goal of this task is to implement a decentralized lending contract that allows:
- Borrowers to collateralize their NFTs in order to take a loan;
- Lenders to lent their tokens;
- Liquidate a loan

There are no limits to the degree of difficulty with which this contract is to be implemented, the functionality to be added or data structures to be used, but there are minimum requirements.

### Requirements:

#### Actors
##### Borrower
Each user can collateralize his/her own NFT, the contract must therefore manage each user's NFT deposit.
Each user wishing to request a loan will have to enter:
- Requested token
- Quantity
- Duration
- Interest

##### Lender
Every user can became a lender accepting the borrower proposal.
Each lender has the right to seize the collateral if the debt is not paid on time.

#### Additional feature
Further features can be thought of, describing and justifying them, then they can be implemented e.g. downward auction on interest, tokenize lender position, extending loan period.
### Judging Criteria:
Participants will be evaluated based on the following criteria:
- *Usability*: The user interface or interaction mechanism should be user-friendly, making it easy for users to understand and interact with the contract.
- *Innovation*: Participants will receive extra recognition for incorporating unique or creative features that enhance the lending experience.
- *Code Quality*: The code should be well-structured, readable, and maintainable.

### Prizes:
Participants with the most impressive and functional NFT as collateral contracts will be eligible for prizes:
##### 1°: 3000 gALGO.
##### 2°: 1500 gALGO.
##### 3°:  500 gALGO. 

## Setup and Run

### File structure
1. [Loan smart contract](app.py) written with [PyTeal](https://github.com/algorand/pyteal) and [Beaker](https://github.com/algorand-devrel/beaker)
2. [Python Tests](test_app.py) written with [Beaker](https://github.com/algorand-devrel/beaker) and [pytest](https://docs.pytest.org/en/7.1.x/)

### 1. Install prerequisites 
https://developer.algorand.org/docs/get-started/algokit/

### 2. Install python dependencies

`algokit bootstrap all`

### 3. Start localnet
`algokit localnet start`

### 3. Compile Contract

`poetry run python app.py`

### 4. Python Tests (PyTest)

`poetry run pytest -s`

## TODO
1. Fix test_liquidate_loan -> lender should receive 1 NFT
2. borrower requirement has not been met cause not all borrowers can request for a loan as the data is saved as global states
3. opt_borrower_in_token: you don't need this, and it is not an opt in
4.  When deleting or repaying you send 1 token, but when you request a loan the token amount is not checked
5. Not need end having start and duration
6. borrower requirement has not been met cause not all borrowers can request for a loan as the data is saved as global states
7. opt_borrower_in_token: you don't need this, and it is not an opt in
8. When deleting or repaying you send 1 token, but when you request a loan the token amount is not checked
9. Not need end having start and duration
