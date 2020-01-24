#!/usr/bin/python3
"""
author: Rene Pickhardt (rene.m.pickhardt@ntnu.no)
Date: 24.1.2020
License: MIT

This plugin helps you to construct a route object (to be used with sendpay) which goes over a sequence of node ids. if all these nodeids are on a path of payment channels an onion following this path will be constructed. In the case of missing channels `lightning-cli geroute` is invoked to find partial routs. 

This plugin can be used to create circular onions or to send payments along specific paths if that is necessary (as long as the paths provide enough liquidity). 

I guess this plugin could also be used to simulate the behaviour of trampoline payments.

And of course I imagine you the reader of this message will find even more creative ways of using it.

=== Support:
If you like my work consider a donation at https://patreon.com/renepickhardt or https://tallyco.in/s/lnbook
"""

from pyln.client import Plugin
# import lightning

import itertools


plugin = Plugin(autopatch=True)
d = {}
n = {}


def __pairs(iterable):
    x, y = itertools.tee(iterable)
    next(y, None)
    return zip(x, y)


desc = "gets a route object to be used in send pay over a fixed set of nodes"
@plugin.method("getfixedroute", long_desc=desc)
def getfixedroute(plugin, amount, nodes):
    """
    Construct a fixed route over a list of node ids. 

    If channel exist between consecutive nodes these channels will be used. 
    Otherwise the lightning-cli getroute will be invoked to find partial routes.
    """

    delay = 9
    fees = 0
    result = []
    for src, dest in reversed(list(__pairs(nodes))):
        amount = amount + fees
        key = "{}:{}".format(src, dest)
        if key not in d:
            route = plugin.rpc.getroute(dest, amount, 1,  delay, src)["route"]
            for e in reversed(route):
                result.append(e)
            chan = d["{}:{}".format(src, route[0]["id"])]
            fees = chan["base_fee_millisatoshi"] + amount * \
                chan["fee_per_millionth"] / 1000 / 1000
            delay = result[-1]["delay"] + chan["delay"]

        else:
            chan = d[key]
            # https://github.com/ElementsProject/lightning/blob/edbcb6fa15c1929b72cfa89758d0f94d41d9f1ef/gossipd/routing.h#L253
            direction = 0
            # I guess the following reverses the definition with the der encoding of channels for all my tests the results where the same as in getroute but I am not sure if this is actually correct. please can someone verify and remove this message: https://github.com/ElementsProject/lightning/blob/edbcb6fa15c1929b72cfa89758d0f94d41d9f1ef/gossipd/routing.h#L56
            if dest < src:
                direction = 1

            # c.f: https://github.com/ElementsProject/lightning/blob/edbcb6fa15c1929b72cfa89758d0f94d41d9f1ef/gossipd/routing.c#L381
            style = "legacy"
            # https://github.com/ElementsProject/lightning/blob/edbcb6fa15c1929b72cfa89758d0f94d41d9f1ef/gossipd/routing.c#L2526 and : https://github.com/lightningnetwork/lightning-rfc/blob/master/09-features.md
            features = int(n[dest]["globalfeatures"], 16)
            if features & 0x01 << 8 != 0 or features & 0x01 << 9 != 0:
                style = "tlv"
            entry = {"id": dest, "channel": chan["short_channel_id"], "direction": direction, "msatoshi": amount,
                     "amount_msat": "{}msat".format(amount), "dealy": delay, "style": style}
            result.append(entry)
            fees = chan["base_fee_millisatoshi"] + amount * \
                chan["fee_per_millionth"] / 1000 / 1000
            delay = delay + chan["delay"]

        fees = int(fees)
    result = list(reversed(result))

    # id, chanel, direction, msatoshi, amount_msat, delay, style
    return {"route": result}


desc = "purges the index of the gossip store"
@plugin.method("getfixedroute_purge", long_desc=desc)
def refresh_gossip_info(plugin):
    """
    purges the index gossip store.
    """
    channels = plugin.rpc.listchannels()["channels"]

    for chan in channels:
        d["{}:{}".format(chan["source"], chan["destination"])] = chan

    for u in plugin.rpc.listnodes()["nodes"]:
        n[u["nodeid"]] = u
    return {"result": "successfully reindexed the gossip store."}


@plugin.init()
def init(options, configuration, plugin):
    # info = plugin.rpc.getinfo()
    plugin.log("Plugin fixroute_pay registered")
    refresh_gossip_info(plugin)


plugin.run()
