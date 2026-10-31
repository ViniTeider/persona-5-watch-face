plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.example.persona5watchface"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.example.persona5watchface"
        minSdk = 33
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

    }

    buildTypes {
        release {
            optimization {
                enable = true
                packageScope = setOf("androidx.**", "kotlin.**", "kotlinx.**")
            }
        }
    }
    enableKotlin = false
}

dependencies {
}