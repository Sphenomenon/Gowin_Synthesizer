plugins { id("com.android.library"); kotlin("android") }
android {
    namespace = "cn.gowin.control.ble"
    compileSdk = 35
    buildToolsVersion = "35.0.0"
    defaultConfig { minSdk = 26 }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    api(project(":core:protocol"))
    api("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
