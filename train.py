import sys, traceback, os, spu, importlib.util
import secretflow as sf
import matplotlib.pyplot as plt
import pandas as pd
from secretflow.utils.simulation.datasets import dataset
from secretflow.data.split import train_test_split
from secretflow.ml.nn import SLModel
from secretflow.utils.simulation.datasets import load_bank_marketing
from secretflow.preprocessing.scaler import MinMaxScaler
from secretflow.preprocessing.encoder import LabelEncoder
from secretflow.data.vertical import read_csv
from secretflow.security.privacy import DPStrategy, LabelDP
from secretflow.security.privacy.mechanism.tensorflow import GaussianEmbeddingDP
from secretflow.preprocessing.encoder import OneHotEncoder
import tensorflow as tf
import numpy as np
import logging
from secretflow.data.vertical import read_csv
import re



def get_data(users, spu):
    """获取数据"""

    key_columns = ['ID']
    label_columns = ['ID']

    # 初始化一个空字典来存储路径
    input_path = {}
    # 接受每个用户的输入
    for user in users:
        path = input(f"请输入 {user} 的文件路径: ")
        input_path[user] = path

        
    # input_path = {
    #     alice: '/home/GPH/Documents/Commerce-Security-Governance-Over-privacy-alliance-CSGO-/DataGen/leveled_orders_JD.csv',
    #     bob:  '/home/bbbbhrrrr/CSGO/Commerce-Security-Governance-Over-privacy-alliance-CSGO-/DataGen/leveled_orders_TB.csv',
    #     carol:  '/home/lwzheng/workspace/sf/DataGen/leveled_Credit_score.csv'
    # }

    vdf = read_csv(input_path, spu=spu, keys=key_columns,
                   drop_keys=label_columns, psi_protocl="ECDH_PSI_3PC")
    
    return vdf


def gen_train_data(vdf):
    """生成训练数据"""

    label_JD = vdf["level_JD"]
    label_TB = vdf["level_TB"]
    label = vdf["level_Total"]

    # 删除标签列
    data = vdf.drop(columns=["level_JD", "level_TB", "level_Total"])


    # 对数据进行编码
    encoder = LabelEncoder()
    data['Total_Count_JD'] = encoder.fit_transform(data['Total_Count_JD'])
    data['Total_Count_TB'] = encoder.fit_transform(data['Total_Count_TB'])
    data['Refund_Only_Count_JD'] = encoder.fit_transform(
        data['Refund_Only_Count_JD'])
    data['Refund_Only_Count_TB'] = encoder.fit_transform(
        data['Refund_Only_Count_TB'])
    data['Rental_Not_Returned_Count_JD'] = encoder.fit_transform(
        data['Rental_Not_Returned_Count_JD'])
    data['Rental_Not_Returned_Count_TB'] = encoder.fit_transform(
        data['Rental_Not_Returned_Count_TB'])
    data['Partial_Payment_After_Receipt_Count_JD'] = encoder.fit_transform(
        data['Partial_Payment_After_Receipt_Count_JD'])
    data['Partial_Payment_After_Receipt_Count_TB'] = encoder.fit_transform(
        data['Partial_Payment_After_Receipt_Count_TB'])
    data['Payment_Without_Delivery_Count_JD'] = encoder.fit_transform(
        data['Payment_Without_Delivery_Count_JD'])
    data['Payment_Without_Delivery_Count_TB'] = encoder.fit_transform(
        data['Payment_Without_Delivery_Count_TB'])
    data['Amount_of_Loss_JD'] = encoder.fit_transform(
        data['Amount_of_Loss_JD'])
    data['Amount_of_Loss_TB'] = encoder.fit_transform(
        data['Amount_of_Loss_TB'])
    data['Credit_Score'] = encoder.fit_transform(data['Credit_Score'])

    encoder = OneHotEncoder()
    label_JD = encoder.fit_transform(label_JD)
    label_TB = encoder.fit_transform(label_TB)
    label = encoder.fit_transform(label)

    scaler = MinMaxScaler()
    data = scaler.fit_transform(data)

    # 划分数据集
    random_state = 1234
    train_data, test_data = train_test_split(
        data, train_size=0.85, random_state=random_state
    )
    train_label, test_label = train_test_split(
        label, train_size=0.85, random_state=random_state
    )

    return train_data, test_data, train_label, test_label


def create_base_model(input_dim, output_dim, name='base_model'):
    """创建基础模型"""
    # Create model
    def create_model():
        from tensorflow import keras
        import keras.layers as layers
        import tensorflow as tf

        model = keras.Sequential(
            [
                keras.Input(shape=input_dim),
                layers.Dense(100, activation="relu"),
                layers.Dense(output_dim, activation="relu"),
            ]
        )
        # Compile model
        model.summary()
        model.compile(
            loss='categorical_crossentropy',
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            metrics=["accuracy", tf.keras.metrics.AUC()],
        )
        return model

    return create_model


def create_fuse_model(input_dim, output_dim, party_nums, name='fuse_model'):
    """创建融合模型"""
    def create_model():
        from tensorflow import keras
        import keras.layers as layers
        import tensorflow as tf

        # input
        input_layers = []
        for i in range(party_nums):
            input_layers.append(
                keras.Input(
                    input_dim,
                )
            )

        merged_layer = layers.concatenate(input_layers)
        fuse_layer = layers.Dense(64, activation='relu')(merged_layer)
        output = layers.Dense(output_dim, activation='sigmoid')(fuse_layer)

        model = keras.Model(inputs=input_layers, outputs=output)
        model.summary()

        model.compile(
            loss='categorical_crossentropy',
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            metrics=["accuracy", tf.keras.metrics.AUC()],
        )
        return model

    return create_model

def training(train_data, train_label, test_data, test_label, users):
    """训练模型"""

    alice = users[0]
    bob = users[1]
    carol = users[2]
    # prepare model
    hidden_size = 64

    model_base_alice = create_base_model(6, hidden_size)
    model_base_bob = create_base_model(6, hidden_size)
    carol_model = create_base_model(1, hidden_size)

    model_base_alice()
    model_base_bob()
    carol_model()

    model_fuse = create_fuse_model(
        input_dim=hidden_size, party_nums=3, output_dim=5)
    model_fuse()

    base_model_dict = {alice: model_base_alice,
                       bob: model_base_bob, carol: carol_model}

    # Define DP operations
    train_batch_size = 1000
    gaussian_embedding_dp = GaussianEmbeddingDP(
        noise_multiplier=0.5,
        l2_norm_clip=1.0,
        batch_size=train_batch_size,
        num_samples=train_data.values.partition_shape()[carol][0],
        is_secure_generator=False,
    )
    label_dp = LabelDP(eps=64.0)
    dp_strategy_carol = DPStrategy(label_dp=label_dp)
    dp_strategy_bob = DPStrategy(embedding_dp=gaussian_embedding_dp)
    dp_strategy_alice = DPStrategy(embedding_dp=gaussian_embedding_dp)
    dp_strategy_dict = {alice: dp_strategy_alice,
                        bob: dp_strategy_bob, carol: dp_strategy_carol}
    dp_spent_step_freq = 10

    sl_model = SLModel(
        base_model_dict=base_model_dict,
        device_y=carol,
        model_fuse=model_fuse,
        dp_strategy_dict=dp_strategy_dict,
    )

    history = sl_model.fit(
        train_data,
        train_label,
        validation_data=(test_data, test_label),
        epochs=50,
        batch_size=train_batch_size,
        shuffle=True,
        verbose=1,
        validation_freq=1,
        dp_spent_step_freq=dp_spent_step_freq,
    )               

    # predict the test data
    y_pred = sl_model.predict(test_data)
    print(f"type(y_pred) = {type(y_pred)}")

    print(sf.reveal(y_pred))

    data = sf.reveal(y_pred)

    # 将预测结果转换为 tensor张量

    # 找到最大行数
    max_rows = max(tensor.shape[0] for tensor in data)

    # 填充或裁剪数据，使其形状一致
    padded_data = []
    for tensor in data:
        if tensor.shape[0] < max_rows:
            # 填充
            padding = np.zeros(
                (max_rows - tensor.shape[0], tensor.shape[1]), dtype=np.float32)
            padded_tensor = np.vstack((tensor, padding))
        else:
            # 裁剪
            padded_tensor = tensor[:max_rows, :]
        padded_data.append(padded_tensor)

    # 将数据转换为TensorFlow张量
    tensor = tf.convert_to_tensor(tensor, dtype=tf.float32)
    # 将 tensor 转换为5列的形式
    tensor = tf.reshape(tensor, [-1, 5])

    # 找到每行最大值的索引
    max_indices = tf.argmax(tensor, axis=1)
    # 将索引转换为 one-hot 编码
    predicted_one_hot = tf.one_hot(max_indices, depth=tensor.shape[1])

    # 打印预测结果和真实标签，作为对比
    print(f"predicted_one_hot = {predicted_one_hot}")        

    print(sf.reveal(test_label.partitions[carol].data))

    # Evaluate the model
    evaluator = sl_model.evaluate(test_data, test_label, batch_size=10)
    print(evaluator)

    return history



def show_mode_result(history):
    """显示模型结果"""

    # Plot the change of loss during training
    plt.figure(figsize=(12, 4))
    plt.subplot(1, 3, 1)
    plt.plot(history['train_loss'])
    plt.plot(history['val_loss'])
    plt.title('Model loss')
    plt.ylabel('Loss')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Val'], loc='upper right')

    # Plot the change of accuracy during training
    plt.subplot(1, 3, 2)
    plt.plot(history['train_accuracy'])
    plt.plot(history['val_accuracy'])
    plt.title('Model accuracy')
    plt.ylabel('Accuracy')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Val'], loc='upper left')

    # Plot the Area Under Curve(AUC) of loss during training
    plt.subplot(1, 3, 3)
    plt.plot(history['train_auc_1'])
    plt.plot(history['val_auc_1'])
    plt.title('Model Area Under Curve')
    plt.ylabel('Area Under Curve')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Val'], loc='upper left')

    plt.tight_layout()
    plt.savefig('/home/GPH/Documents/Commerce-Security-Governance-Over-privacy-alliance-CSGO-/model_results.png')
    plt.show()
