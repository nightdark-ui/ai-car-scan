plugins {
    id("com.android.application")
}

android {
    namespace = "com.leonidascan.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.leonidascan.app"
        minSdk = 24
        targetSdk = 34
        versionCode = 11
        versionName = "1.0.0"

        // 只保留手机用的两种 ABI，砍掉 x86/x86_64 可省约 40MB
        ndk {
            abiFilters += listOf("armeabi-v7a", "arm64-v8a")
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    androidResources {
        noCompress += listOf("html", "tflite", "csv", "jpg")
    }

    // AGP 8 默认不生成 BuildConfig，这里打开以便把版本号显示在界面上
    buildFeatures {
        buildConfig = true
    }
}

// ML Kit 会带进 kotlin-stdlib-jdk8 1.6.0，和 camera 的 1.8.x 冲突。
// 1.8.0 之后 jdk7/jdk8 已并入 kotlin-stdlib，统一版本即可消除重复类。
configurations.all {
    resolutionStrategy {
        force("org.jetbrains.kotlin:kotlin-stdlib:1.8.22")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk7:1.8.22")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.8.22")
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")

    // 相机
    implementation("androidx.camera:camera-core:1.3.4")
    implementation("androidx.camera:camera-camera2:1.3.4")
    implementation("androidx.camera:camera-lifecycle:1.3.4")
    implementation("androidx.camera:camera-view:1.3.4")

    // 目标检测（EfficientDet-Lite0 / COCO）
    implementation("org.tensorflow:tensorflow-lite:2.16.1")

    // 车牌 OCR（中文识别，含省级简称）
    implementation("com.google.mlkit:text-recognition-chinese:16.0.0")
}
