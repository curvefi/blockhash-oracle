"""Native chains keep their own record of Ethereum, so they need neither bridge: a committer
contract there reads that record and is the oracle's only committer, and no relay is deployed.

One table for deploy.ipynb, config.ipynb and set_dvn.ipynb, so the three cannot disagree on which
chains are native. "committer" names the contract under contracts/native/, "args" are its
constructor arguments after the oracle's address.
"""

NATIVE_CHAINS = {
    "mainnets": {
        "taiko": {
            "committer": "TaikoBlockCommitter",
            "args": [
                "0x1670000000000000000000000000000000000005",  # signal service
                "0x1670000000000000000000000000000000010001",  # anchor
            ],
        },
    },
    "testnets": {},
}
