// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract PostVerification {

    struct Record {
        uint256 timestamp;
        address submitter;
        bool exists;
    }

    mapping(bytes32 => Record) private records;

    event HashStored(
        bytes32 indexed dataHash,
        uint256 timestamp,
        address indexed submitter
    );

    function storeHash(bytes32 dataHash) external {
        require(!records[dataHash].exists, "Hash already exists");

        records[dataHash] = Record({
            timestamp: block.timestamp,
            submitter: msg.sender,
            exists: true
        });

        emit HashStored(
            dataHash,
            block.timestamp,
            msg.sender
        );
    }

    function verifyHash(bytes32 dataHash)
        external
        view
        returns (
            bool exists,
            uint256 timestamp,
            address submitter
        )
    {
        Record memory record = records[dataHash];

        return (
            record.exists,
            record.timestamp,
            record.submitter
        );
    }
}