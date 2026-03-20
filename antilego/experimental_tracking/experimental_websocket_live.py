from py_clob_client.client import ClobClient

host: str = "https://clob.polymarket.com"
key: str = "<YOUR KEY>"
chain_id: int = 137 # No need to adjust this
POLYMARKET_PROXY_ADDRESS: str = "" # This is the address you deposit/send USDC to to FUND your Polymarket account.

### Initialization of a client using a Polymarket Proxy associated with an Email/Magic account. If you login with your email use this example.
client = ClobClient(host, key=key, chain_id=chain_id, signature_type=1, funder=POLYMARKET_PROXY_ADDRESS)

derived_creds = client.derive_api_key()

print(derived_creds)



from websocket import WebSocketApp
import json
import time
import threading

import orderbook

MARKET_CHANNEL = "market"
USER_CHANNEL = "user"

class WebSocketOrderBook:

    def __init__(self, channel_type, url, data, auth, message_callback, verbose):
        self.channel_type = channel_type
        self.url = url
        self.data = data
        self.auth = auth
        self.message_callback = message_callback
        self.verbose = verbose
        furl = url + "/ws/" + channel_type
        self.ws = WebSocketApp(
            furl,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        self.orderbooks = orderbook.OrderBook(data[0])

    def on_message(self, ws, message):

        print(message)

        if message[0:4] == "PONG":
            return

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            if self.verbose:
                print("Non-JSON message:", message)
            return

        if isinstance(data, list):
            for entry in data:
                self.orderbooks.route_message(entry)
        else:
            self.orderbooks.route_message(data)

        print(self.orderbooks)

    def on_error(self, ws, error):
        print("Error: ", error)
        exit(1)

    def on_close(self, ws, close_status_code, close_msg):
        print("closing")
        exit(0)

    def on_open(self, ws):
        if self.channel_type == MARKET_CHANNEL:
            ws.send(json.dumps({"assets_ids": self.data, "type": MARKET_CHANNEL}))
        elif self.channel_type == USER_CHANNEL and self.auth:
            ws.send(
                json.dumps(
                    {"markets": self.data, "type": USER_CHANNEL, "auth": self.auth}
                )
            )
        else:
            exit(1)

        thr = threading.Thread(target=self.ping, args=(ws,))
        thr.start()

    def ping(self, ws):
        while True:
            ws.send("PING")
            time.sleep(10)

    def run(self):
        self.ws.run_forever()

if __name__ == "__main__":

    url = "wss://ws-subscriptions-clob.polymarket.com"

    #Complete these by exporting them from your initialized client. 
    api_key = derived_creds.api_key
    api_secret = derived_creds.api_secret
    api_passphrase = derived_creds.api_passphrase

    asset_ids = [
        "59971444048982820090749128753331211858318529324980291176754797725178535217659",
    ]
    # condition_ids = [] # no really need to filter by this one

    auth = {"apiKey": api_key, "secret": api_secret, "passphrase": api_passphrase}

    market_connection = WebSocketOrderBook(
        MARKET_CHANNEL, url, asset_ids, auth, None, True
    )
    # user_connection = WebSocketOrderBook(
    #     USER_CHANNEL, url, condition_ids, auth, None, True
    # )

    try:
        market_connection.run()
    except KeyboardInterrupt:
        print("END")
    # user_connection.run()