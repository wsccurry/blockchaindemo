import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4
import requests
from flask import Flask, jsonify, request
from threading import Thread


class BlockChain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()
        # 创建创世区块
        self.new_block(proof=100, previous_hash=1)

    def new_block(self, proof, previous_hash=None):
        """
        创建一个区块并加到区块链中
        :param proof: <int>由工作量证明算法给出的证明
        :param privious_hash: (Optional)<str>上一个区块的哈希值
        :return: <dict>返回一个区块
        """
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1])
        }
        self.current_transactions = []
        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        创建一个新的交易并加到下一个挖矿出的区块
        :param sender:  <str>发送者的地址
        :param recipient: <str>接受者的地址
        :param amount: <int>数量（金额）
        :return: <int>返回接受这个交易的区块的下标
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount
        })
        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        """
        将一个区块做哈希运算，得到区块的哈希值
        :param block: <dict>区块
        :return: <str>区块哈希值
        """
        block_str = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_str).hexdigest()

    # 返回区块链中的最后一个区块
    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        """
        一个简单的工作量证明
        - 找到数字b，使得hash(ab)的值的前四位为0
        - a是上一个区块的证明，b是新区块的证明

        :param last_proof:<int>
        :return:<int>
        """
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        验证hash(last_proof*proof)值的前四位为0
        :param last_proof: 上一个区块的证明
        :param proof: 新区块的证明
        :return: <bool>
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def regist_node(self, address):
        """
        在节点集合中添加新节点
        :param address: <str>节点地址，比如"http://localhost:5050"
        :return:None
        """
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain):
        """
        检查区块链是否有效
        :param chain: <list>一个区块链
        :return: <bool>True代表有效，False代表无效
        """
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")

            # 检查区块的哈希是否正确
            if block['previous_hash'] != BlockChain.hash(last_block):
                return False

            # 检查工作量证明是否正确:
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        """
        共识算法，解决冲突，取网络中最长的区块链为本节点的区块链
        :return:<bool>True代表本地节点的区块链被取代，否则不是
        """
        # 存储在网络中的所有节点
        neighbours = self.nodes

        new_chain = None
        max_length = len(self.chain)

        for node in neighbours:
            response = requests.get(f'http://{node}/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # 检查长度是否更长以及链条是否有效
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain
        if new_chain:
            self.chain = new_chain
            return True


# 实例化节点
app = Flask(__name__)

# 为该节点生成一个全局唯一的地址，可以理解为我们挖矿的比特币地址
node_identifier = str(uuid4()).replace('-', '')

# 实例化区块链
blockchain = BlockChain()


@app.route('/mine', methods=['GET'])
def mine():
    # 运行工作量证明算法得到新区块的证明
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # 给矿工的工作给予奖励
    blockchain.new_transaction(sender='0', recipient=node_identifier, amount=1)

    # 新增区块加到区块链上
    previous_hash = BlockChain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash']
    }
    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transacion():
    values = request.get_json()

    # 检查Post请求数据中是否包含了指定的字段
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # 新建一个交易
    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get('nodes')
    if nodes is None:
        return "Error：Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.regist_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes)
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()
    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }
    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)











