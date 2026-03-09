# order book data structure

class OrderBook:

    def __init__(self, asset_id, initial_book={}):

        self.asset_id = asset_id

        self.bids = {}
        self.asks = {}
        self.last_update = -1
        self.best_bid = -1
        self.best_ask = -1

        if initial_book:
            self.set_book(initial_book)

    def __repr__(self):
        s = "\n\033[31m"
        for k in sorted(self.asks.keys(), reverse=True):
            s += str(k) + ": " + str(self.asks[k]) + "\n"
        s += "\033[32m"
        for k in sorted(self.bids.keys(), reverse=True):
            s += str(k) + ": " + str(self.bids[k]) + "\n"
        return s + "\033[37m"

    def set_book(self, book):
        for bid in book["bids"]:
            self.bids[float(bid["price"])] = float(bid["size"])
        for ask in book["asks"]:
            self.asks[float(ask["price"])] = float(ask["size"])
        self.last_update = int(book["timestamp"])
        self.best_bid = max(self.bids.keys())
        self.best_ask = min(self.asks.keys())

    def update_book(self, price_change):
        p = float(price_change["price"])
        s = float(price_change["size"])
        if s == 0:
            if p <= self.best_bid:
                del self.bids[p]
            else:
                del self.asks[p]
            self.best_bid = float(price_change["best_bid"])
            self.best_ask = float(price_change["best_ask"])
            return
        self.best_bid = float(price_change["best_bid"])
        self.best_ask = float(price_change["best_ask"])
        if p <= self.best_bid:
            self.bids[p] = s
        else:
            self.asks[p] = s

    def route_message(self, msg):
        if msg["event_type"] == "book":
            self.set_book(msg)
        else:
            for pc in msg["price_changes"]:
                if pc["asset_id"] == self.asset_id:
                    self.update_book(pc)